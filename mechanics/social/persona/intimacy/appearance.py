from __future__ import annotations
from .constants import *
import json
import hashlib
import re
from typing import Dict, Any, List, Optional
from ..core import *

def extract_appearance_from_text(text: str, name: str = "") -> Dict[str, str]:
    """Extracts physical appearance traits (eyes, stature, coat/fur, hair) directly from narrative text."""
    if not text or not isinstance(text, str):
        return {}

    target = text
    if name and len(name) >= 3:
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]
        matching = [s for s in sentences if name.lower() in s.lower()]
        if matching:
            target = " ".join(matching)

    extracted = {}

    # 1. Eyes
    m_eye = re.search(
        r"\b(piercing amber|smoldering amber|amber|burning gold|golden|molten gold|gold|ice blue|sapphire blue|blue|emerald green|jade green|green|hazel|chestnut|ruby red|ruby|violet|amethyst|topaz|grey|gray|dark slate|copper)\s+eyes?\b",
        target,
        re.IGNORECASE
    )
    if m_eye:
        extracted["eye_color"] = m_eye.group(1).lower().replace(" ", "_")

    # 2. Stature
    m_stat = re.search(
        r"\b(tall|towering|statuesque|short|petite|compact|lanky|broad|slender|average[\s\-_]height|average)\b",
        target,
        re.IGNORECASE
    )
    if m_stat:
        extracted["stature"] = m_stat.group(1).lower().replace(" ", "_")

    # 3. Coat / Fur / Scales
    m_coat = re.search(
        r"\b(snow[\s\-_]white|pure white|white|midnight[\s\-_]black|jet[\s\-_]black|black|ash[\s\-_]gray|silver[\s\-_]white|frost[\s\-_]white|golden[\s\-_]amber|golden|rust[\s\-_]red|tawny|chestnut|charcoal|fawn|cream|calico|spotted|striped)\s+(fur|coat|scales?|feathers?)\b",
        target,
        re.IGNORECASE
    )
    if m_coat:
        extracted["coat_color"] = f"{m_coat.group(1).lower()} {m_coat.group(2).lower()}"
        if "scale" in m_coat.group(2).lower():
            extracted["skin_type"] = "scaly"
        elif "fur" in m_coat.group(2).lower():
            extracted["skin_type"] = "furry"

    # 4. Hair
    m_hair = re.search(
        r"\b(snow[\s\-_]white|platinum|golden[\s\-_]blonde|blonde|black|dark slate|auburn|chestnut|brown|silver)\s+hair\b",
        target,
        re.IGNORECASE
    )
    if m_hair:
        extracted["hair_color"] = m_hair.group(1).lower()

    return extracted


def normalize_appearance(raw_app: Dict[str, Any] | str = None, gender: str = "", race: str = "human", scen_key: str = "fantasy", desc: Any = "", traits: List[str] = None, role: str = "") -> Dict[str, Any]:
    """Normalizes raw appearance data, applying smart stature defaults and gating NSFW fields."""
    if isinstance(raw_app, str):
        try:
            app_dict = json.loads(raw_app)
        except Exception:
            app_dict = {}
    elif isinstance(raw_app, dict):
        app_dict = dict(raw_app)
    else:
        app_dict = {}

    desc_text = str(desc or "")
    extracted_app = extract_appearance_from_text(desc_text)

    seed_str = (desc_text + "_" + str(race)).encode("utf-8")
    hash_val = int(hashlib.md5(seed_str).hexdigest(), 16) if seed_str else 0
    raw_g = (gender or (app_dict.get("gender") if isinstance(app_dict, dict) else "") or "").strip().lower()
    is_male = any(kw in raw_g for kw in ("male", "man", "boy", "lord", "he", "him", "his")) and not any(kw in raw_g for kw in ("female", "woman"))

    raw_eye = app_dict.get("eye_color") or app_dict.get("eyes")
    if raw_eye and str(raw_eye).strip().lower() not in ("unknown", ""):
        eye = str(raw_eye).strip().lower().replace(" ", "_")
    elif extracted_app.get("eye_color"):
        eye = extracted_app["eye_color"]
    else:
        spec = get_species_key_from_race(race, desc=desc_text)
        if spec and spec in SPECIES_TEMPLATES and SPECIES_TEMPLATES[spec].get("eyes"):
            pool = SPECIES_TEMPLATES[spec]["eyes"]
            eye = pool[hash_val % len(pool)].lower().replace(" ", "_")
        else:
            eye = "blue"

    # Skin color / coat features
    skin_color = str(app_dict.get("skin_color") or app_dict.get("skin") or "").strip()
    skin_type = str(app_dict.get("skin_type") or app_dict.get("coat_type") or extracted_app.get("skin_type") or "").strip().lower()
    coat_color = str(app_dict.get("coat_color") or app_dict.get("fur_color") or app_dict.get("scale_color") or app_dict.get("feather_color") or app_dict.get("coat") or extracted_app.get("coat_color") or "").strip()
    if not coat_color and not is_half_beast_race(race):
        spec = get_species_key_from_race(race, desc=desc_text)
        if spec and spec in SPECIES_TEMPLATES:
            coats = SPECIES_TEMPLATES[spec].get("coats") or SPECIES_TEMPLATES[spec].get("scales")
            if coats:
                coat_color = coats[hash_val % len(coats)]
    if not skin_type and not is_half_beast_race(race):
        spec = get_species_key_from_race(race, desc=desc_text)
        if spec:
            if is_scaly_race(race) or spec in ("reptile", "dragon", "snake"):
                skin_type = "scaly"
            elif spec == "bird":
                skin_type = "feathered"
            else:
                skin_type = "furry"

    # Hair handling
    hair_raw = app_dict.get("hair")
    if isinstance(hair_raw, dict):
        h_color = str(hair_raw.get("color") or app_dict.get("hair_color") or "").strip().lower()
        h_len = str(hair_raw.get("length") or app_dict.get("hair_length") or "").strip().lower()
        h_style = str(hair_raw.get("style") or app_dict.get("hair_style") or "").strip().lower()
    else:
        h_color = str(app_dict.get("hair_color") or "").strip().lower()
        h_len = str(app_dict.get("hair_length") or "").strip().lower()
        h_style = str(app_dict.get("hair_style") or "").strip().lower()

    if not h_len:
        h_len = DIVERSE_HAIR_LENGTHS_MALE[hash_val % len(DIVERSE_HAIR_LENGTHS_MALE)] if is_male else DIVERSE_HAIR_LENGTHS_FEMALE[hash_val % len(DIVERSE_HAIR_LENGTHS_FEMALE)]
    if not h_style:
        h_style = DIVERSE_MALE_HAIR_STYLES[hash_val % len(DIVERSE_MALE_HAIR_STYLES)] if is_male else DIVERSE_FEMALE_HAIR_STYLES[hash_val % len(DIVERSE_FEMALE_HAIR_STYLES)]
    if not h_color:
        if extracted_app.get("hair_color"):
            h_color = extracted_app["hair_color"]
        else:
            coat_col = coat_color or app_dict.get("coat_color") or app_dict.get("scale_color") or app_dict.get("fur_color")
            nat_inferred = infer_natural_hair_color_from_coat(coat_col, race)
            if nat_inferred and nat_inferred != "natural":
                h_color = nat_inferred
            elif coat_col and "snow" in coat_col.lower():
                h_color = "snow-white"
            else:
                human_tones = ["jet black", "chestnut brown", "golden blonde", "dark slate", "auburn", "caramel brown", "honey blonde"]
                h_color = human_tones[hash_val % len(human_tones)]

    # Stature handling (with smart race default & narrative extraction)
    default_stat = get_default_stature_for_race(race)
    if app_dict.get("stature"):
        stature = str(app_dict["stature"]).strip().lower()
    elif extracted_app.get("stature"):
        stature = extracted_app["stature"]
    else:
        stature = str(default_stat).strip().lower()
    
    # Distinctive features, Outfit style & Physique
    distinctive_features = str(app_dict.get("distinctive_features") or app_dict.get("features") or app_dict.get("marks") or "").strip()
    if not distinctive_features:
        spec = get_species_key_from_race(race, desc=desc_text)
        if spec and spec in SPECIES_TEMPLATES:
            feats_key = "hybrid_features" if is_half_beast_race(race) else "beastfolk_features"
            feat_pool = SPECIES_TEMPLATES[spec].get(feats_key) or SPECIES_TEMPLATES[spec].get("beastfolk_features") or []
            if feat_pool:
                distinctive_features = feat_pool[hash_val % len(feat_pool)]

    outfit_style = str(app_dict.get("outfit_style") or app_dict.get("outfit") or app_dict.get("clothing") or "").strip()

    raw_g = (gender or (app_dict.get("gender") if isinstance(app_dict, dict) else "") or "").strip().lower()
    is_male = any(kw in raw_g for kw in ("male", "man", "boy", "lord", "he", "him", "his")) and not any(kw in raw_g for kw in ("female", "woman"))

    seed_str = (str(desc) + "_" + str(race)).encode("utf-8")
    hash_val = int(hashlib.md5(seed_str).hexdigest(), 16) if seed_str else 0

    physique = str(app_dict.get("physique") or "").strip()
    if not physique:
        if is_male:
            physique = PHYSIQUE_MALE_TEMPLATES[hash_val % len(PHYSIQUE_MALE_TEMPLATES)]
        else:
            physique = PHYSIQUE_FEMALE_TEMPLATES[hash_val % len(PHYSIQUE_FEMALE_TEMPLATES)]

    result = {
        "eye_color": eye,
        "hair_color": h_color,
        "hair_length": h_len,
        "hair_style": h_style,
        "stature": stature,
        "physique": physique,
    }
    if skin_color:
        result["skin_color"] = skin_color
    if skin_type:
        result["skin_type"] = skin_type
    if coat_color:
        result["coat_color"] = coat_color
    if distinctive_features:
        result["distinctive_features"] = distinctive_features
    if outfit_style:
        result["outfit_style"] = outfit_style

    # Dyed hair and natural hair tracking for beastfolk / furred / scaly races
    is_half = is_half_beast_race(race)
    is_beast = is_half or any(k in str(race).lower() for k in ("beastfolk", "beast", "fox", "cat", "wolf", "neko", "kitsune", "rabbit", "bunny", "tiger", "lion", "bear", "mouse", "reptile", "dragon", "snake", "bird", "avian")) or is_scaly_race(race) or ("fur" in str(coat_color).lower()) or ("scale" in str(coat_color).lower()) or ("feather" in str(coat_color).lower()) or (skin_type in ("furry", "scaly", "feathered"))
    is_dyed_explicit = bool(app_dict.get("is_dyed"))
    contrasting = is_contrasting_shade(coat_color, h_color) if is_beast and coat_color else False

    if is_beast and (is_dyed_explicit or contrasting):
        result["is_dyed"] = True
        natural_color = str(app_dict.get("natural_hair_color") or "").strip().lower()
        if not natural_color or natural_color in ("unknown", "natural", h_color):
            natural_color = infer_natural_hair_color_from_coat(coat_color, race)
        result["natural_hair_color"] = natural_color
    elif app_dict.get("natural_hair_color"):
        result["natural_hair_color"] = str(app_dict.get("natural_hair_color")).strip().lower()
        if is_dyed_explicit:
            result["is_dyed"] = True

    # Scenario-gated NSFW body attributes
    has_explicit_intimate = any(
        app_dict.get(k) for k in (
            "breast_size", "penis_size", "turn_ons", "sensitive_spots",
            "fetishes", "intimate_demeanor", "intimate_dynamic",
            "act_likes", "act_dislikes", "undergarments", "bra", "underwear",
            "predetermined_intercourse", "intercourse_experience", "intimate_revealed"
        )
    )
    if is_nsfw_scenario(scen_key) or has_explicit_intimate:
        def _clean_nsfw_val(val: Any) -> str:
            v_str = str(val or "").strip().lower()
            if v_str in ("", "n/a", "none", "null", "unknown", "false", "0"):
                return ""
            return str(val).strip()

        b_size = _clean_nsfw_val(app_dict.get("breast_size"))
        p_size = _clean_nsfw_val(app_dict.get("penis_size"))

        effective_traits = traits if traits is not None else (app_dict.get("traits") or [])
        effective_role = role or app_dict.get("role", "")
        if is_male:
            if p_size:
                result["penis_size"] = p_size
            else:
                result["penis_size"] = "average"
            demeanor_fallback = infer_intimate_demeanor_from_traits(desc=desc, race=race, gender="male", traits=effective_traits, role=effective_role)
            dynamic_fallback = infer_intimate_dynamic_from_traits(desc=desc, race=race, gender="male", traits=effective_traits, role=effective_role)
        else:
            if b_size:
                result["breast_size"] = b_size
            else:
                physique_lower = str(physique).lower()
                if any(w in physique_lower for w in ("petite", "slender", "lithe", "lean", "flat")):
                    cup_pool = ["Petite A-Cup", "Modest B-Cup", "Perky B-Cup", "Soft A-Cup"]
                elif any(w in physique_lower for w in ("voluptuous", "curvy", "busty", "full-figured", "stacked", "hourglass")):
                    cup_pool = ["Voluptuous D-Cup", "Generous DD-Cup", "Heavy D-Cup", "Bountiful E-Cup"]
                elif any(w in physique_lower for w in ("toned", "athletic", "muscular")):
                    cup_pool = ["Firm & Perky B-Cup", "Toned C-Cup", "Athletic B-Cup", "Shapely C-Cup"]
                else:
                    cup_pool = ["Modest B-Cup", "Shapely C-Cup", "Full C-Cup", "Voluptuous D-Cup"]
                result["breast_size"] = cup_pool[hash_val % len(cup_pool)]
            demeanor_fallback = infer_intimate_demeanor_from_traits(desc=desc, race=race, gender="female", traits=effective_traits, role=effective_role)
            dynamic_fallback = infer_intimate_dynamic_from_traits(desc=desc, race=race, gender="female", traits=effective_traits, role=effective_role)

        dem_val = app_dict.get("intimate_demeanor") or app_dict.get("demeanor")
        if not is_valid_persona_attribute_string(dem_val):
            dem_val = demeanor_fallback
        result["intimate_demeanor"] = str(dem_val).strip()

        dyn_val = app_dict.get("intimate_dynamic") or app_dict.get("dynamic")
        if not is_valid_persona_attribute_string(dyn_val):
            dyn_val = dynamic_fallback
        result["intimate_dynamic"] = str(dyn_val).strip()

        openness_fallback = infer_erotic_openness_from_traits(desc=desc, race=race, gender=gender, traits=effective_traits, role=effective_role)
        open_val = app_dict.get("erotic_openness") or app_dict.get("openness")
        if not is_valid_persona_attribute_string(open_val):
            open_val = openness_fallback
        result["erotic_openness"] = str(open_val).strip()

        # Dynamic procedural generator for fallback with dynamic synergy
        dyn_intimate = generate_dynamic_intimate_attributes(hash_val, race=race, gender=gender, dynamic=result["intimate_dynamic"], openness=result["erotic_openness"])

        # 3-Track Experience: Intercourse, Oral, Manual
        mems = app_dict.get("intimate_memories") or []

        # Analyze intimate memories for milestone evidence
        has_oral_give = False
        has_oral_rec = False
        has_manual_give = False
        has_manual_rec = False
        has_intercourse_mem = False

        for m in mems:
            m_l = str(m).lower()
            if any(k in m_l for k in ORAL_GIVE_MEMORY_KEYWORDS):
                has_oral_give = True
            if any(k in m_l for k in ORAL_RECEIVE_MEMORY_KEYWORDS):
                has_oral_rec = True
            if any(k in m_l for k in MANUAL_GIVE_MEMORY_KEYWORDS):
                has_manual_give = True
            if any(k in m_l for k in MANUAL_RECEIVE_MEMORY_KEYWORDS):
                has_manual_rec = True
            if any(k in m_l for k in INTERCOURSE_MEMORY_KEYWORDS):
                has_intercourse_mem = True

        had_first_time = bool(app_dict.get("had_first_time_with_player"))

        # 1. Determine Predetermined Intercourse (Immutable Backstory Anchor)
        pred_intercourse = str(app_dict.get("predetermined_intercourse") or "").strip().lower()
        if not pred_intercourse or pred_intercourse not in INTERCOURSE_STATES:
            if intercourse_input := str(app_dict.get("intercourse_experience") or app_dict.get("intercourse") or "").strip().lower():
                if intercourse_input in INTERCOURSE_STATES:
                    pred_intercourse = intercourse_input
            if not pred_intercourse or pred_intercourse not in INTERCOURSE_STATES:
                pred_intercourse = dyn_intimate.get("intercourse") or "virgin"
        else:
            intercourse_input = str(app_dict.get("intercourse_experience") or app_dict.get("intercourse") or "").strip().lower()

        # 2. Determine Active Intercourse State (Subordinate to Backstory Anchor & Verified Milestones)
        if has_intercourse_mem:
            intercourse_val = "non_virgin"
        elif pred_intercourse == "virgin":
            if had_first_time and intercourse_input == "non_virgin":
                intercourse_val = "non_virgin"
            elif mems:
                intercourse_val = "virgin"
            else:
                intercourse_val = "virgin"
        elif had_first_time and intercourse_input == "non_virgin":
            intercourse_val = "non_virgin"
        elif intercourse_input in INTERCOURSE_STATES and intercourse_input != "unknown":
            if pred_intercourse == "virgin" and intercourse_input == "non_virgin":
                intercourse_val = "virgin"
            else:
                intercourse_val = intercourse_input
        elif pred_intercourse == "virgin":
            intercourse_val = "virgin"
        elif pred_intercourse == "non_virgin":
            intercourse_val = "non_virgin"
        else:
            intercourse_val = dyn_intimate["intercourse"]

        # 3. Determine Active Oral State
        oral_input = str(app_dict.get("oral_experience") or app_dict.get("oral") or "").strip().lower()
        if pred_intercourse == "virgin":
            if mems:
                if has_oral_give and has_oral_rec:
                    oral_val = "has_done_and_received_oral"
                elif has_oral_give:
                    oral_val = "has_done_oral"
                elif has_oral_rec:
                    oral_val = "has_received_oral"
                elif oral_input in ORAL_INTIMACY_STATES and oral_input not in ("inexperienced", "unknown"):
                    oral_val = oral_input
                else:
                    oral_val = oral_input if oral_input == "inexperienced" else dyn_intimate.get("oral", "inexperienced")
            elif oral_input in ORAL_INTIMACY_STATES and oral_input not in ("unknown",):
                # Preserve explicit 'inexperienced' — only use dyn_intimate if truly unset
                oral_val = oral_input
            else:
                oral_val = dyn_intimate.get("oral", "inexperienced")
        elif oral_input in ORAL_INTIMACY_STATES and oral_input != "unknown":
            oral_val = oral_input
        elif pred_intercourse == "non_virgin":
            oral_val = dyn_intimate["oral"]
        else:
            oral_val = dyn_intimate["oral"]

        if pred_intercourse != "virgin":
            if has_oral_give:
                oral_val = merge_oral_states(oral_val, "has_done_oral")
            if has_oral_rec:
                oral_val = merge_oral_states(oral_val, "has_received_oral")

        # 4. Determine Active Manual State
        manual_input = str(app_dict.get("manual_experience") or app_dict.get("manual") or "").strip().lower()
        if pred_intercourse == "virgin":
            if mems:
                if has_manual_give and has_manual_rec:
                    manual_val = "has_done_and_received_manual"
                elif has_manual_give:
                    manual_val = "has_done_manual"
                elif has_manual_rec:
                    manual_val = "has_received_manual"
                elif manual_input in MANUAL_INTIMACY_STATES and manual_input not in ("inexperienced", "unknown"):
                    manual_val = manual_input
                else:
                    manual_val = manual_input if manual_input == "inexperienced" else dyn_intimate.get("manual", "inexperienced")
            elif manual_input in MANUAL_INTIMACY_STATES and manual_input not in ("unknown",):
                # Preserve explicit 'inexperienced' — only use dyn_intimate if truly unset
                manual_val = manual_input
            else:
                manual_val = dyn_intimate.get("manual", "inexperienced")
        elif manual_input in MANUAL_INTIMACY_STATES and manual_input != "unknown":
            manual_val = manual_input
        elif pred_intercourse == "non_virgin":
            manual_val = dyn_intimate["manual"]
        else:
            manual_val = dyn_intimate["manual"]

        if pred_intercourse != "virgin":
            if has_manual_give:
                manual_val = merge_manual_states(manual_val, "has_done_manual")
            if has_manual_rec:
                manual_val = merge_manual_states(manual_val, "has_received_manual")

        result["predetermined_intercourse"] = pred_intercourse
        result["intercourse_experience"] = intercourse_val
        result["oral_experience"] = oral_val
        result["manual_experience"] = manual_val

        # Turn-ons (Physical + Action)
        custom_turns = clean_attribute_list_string(app_dict.get("turn_ons"))
        if is_valid_persona_attribute_string(custom_turns):
            sanitized_turns = sanitize_sensitive_spots_for_species(custom_turns, race=race, distinctive_features=result.get("distinctive_features", ""))
            result["turn_ons"] = sanitized_turns
        elif custom_turns and custom_turns.lower() == "none":
            result["turn_ons"] = ""
        else:
            result["turn_ons"] = dyn_intimate["turn_ons"]

        # Sensitive Spots (Erogenous Zones)
        custom_spots = clean_attribute_list_string(app_dict.get("sensitive_spots") or app_dict.get("erogenous_zones"))
        if is_valid_persona_attribute_string(custom_spots):
            sanitized_spots = sanitize_sensitive_spots_for_species(custom_spots, race=race, distinctive_features=result.get("distinctive_features", ""))
            result["sensitive_spots"] = sanitized_spots
        elif custom_spots and custom_spots.lower() == "none":
            result["sensitive_spots"] = ""
        else:
            result["sensitive_spots"] = result["turn_ons"]

        # Fetishes & Kinks: store full cleaned value (no truncation after first comma)
        custom_fetishes = clean_attribute_list_string(app_dict.get("fetishes"))
        if is_valid_persona_attribute_string(custom_fetishes):
            result["fetishes"] = custom_fetishes
        elif custom_fetishes and custom_fetishes.lower() in ("none", "none (vanilla)"):
            result["fetishes"] = "None (Vanilla)"
        else:
            result["fetishes"] = dyn_intimate["fetishes"]

        # Act & Position Preferences: Likes & Dislikes
        custom_likes = clean_attribute_list_string(app_dict.get("act_likes") or app_dict.get("preferred_acts"))
        custom_dislikes = clean_attribute_list_string(app_dict.get("act_dislikes") or app_dict.get("disliked_acts"))
        result["act_likes"] = custom_likes if is_valid_persona_attribute_string(custom_likes) else dyn_intimate["act_likes"]
        result["act_dislikes"] = custom_dislikes if is_valid_persona_attribute_string(custom_dislikes) else dyn_intimate["act_dislikes"]

        # Undergarments (Bra & Underwear)
        custom_under = app_dict.get("undergarments")
        if isinstance(custom_under, dict) and (custom_under.get("bra") or custom_under.get("underwear")):
            result["undergarments"] = {
                "bra": str(custom_under.get("bra", "")).strip(),
                "underwear": str(custom_under.get("underwear", "")).strip()
            }
        elif isinstance(custom_under, str) and custom_under.strip() and custom_under.lower() not in ("unknown", "n/a", "none"):
            if is_male:
                result["undergarments"] = {"bra": "", "underwear": custom_under.strip()}
            else:
                result["undergarments"] = {"bra": custom_under.strip(), "underwear": f"Matching {custom_under.strip()}"}
        elif app_dict.get("bra") or app_dict.get("underwear"):
            result["undergarments"] = {
                "bra": str(app_dict.get("bra", "")).strip(),
                "underwear": str(app_dict.get("underwear", "")).strip()
            }
        else:
            result["undergarments"] = dyn_intimate["undergarments"]

    # Preserve all revealed flags and metadata state from input dictionary
    for flag_k in (
        "intimate_revealed", "intercourse_revealed", "oral_revealed", "manual_revealed",
        "demeanor_revealed", "dynamic_revealed", "openness_revealed",
        "sensitive_spots_revealed", "turn_ons_revealed", "fetishes_revealed",
        "act_preferences_revealed", "mannerisms_revealed", "underwear_revealed", "all_revealed",
        "had_first_time_with_player", "intimate_memories", "past_intimate_history", "past_intimate_entries"
    ):
        if flag_k in app_dict:
            result[flag_k] = app_dict[flag_k]

    result = enforce_intimacy_safeguard_invariants(result)
    return result

def merge_appearance_safely(existing_app: Dict[str, Any], incoming_app: Dict[str, Any]) -> Dict[str, Any]:
    """
    Safely merges incoming appearance data into an established character's appearance dict.
    Strictly preserves immutable core physical traits (eyes, hair, stature, physique, fur/coat/skin,
    distinctive features, breast/penis size, predetermined virginity) once established, preventing
    arbitrary mutations from LLM re-introductions, generic turn fallbacks, or ambient updates.
    Live active virginity and experience dynamically advance forward upon intimate encounters via a one-way ratchet.
    """
    merged = dict(existing_app or {})
    if not incoming_app or not isinstance(incoming_app, dict):
        return merged

    # 1. Snapshot one-way reveal flags BEFORE merging
    _one_way_true_flags = (
        "intercourse_revealed", "oral_revealed", "manual_revealed",
        "intimate_revealed", "demeanor_revealed", "dynamic_revealed", "openness_revealed",
        "sensitive_spots_revealed", "turn_ons_revealed", "fetishes_revealed",
        "act_preferences_revealed", "underwear_revealed", "had_first_time_with_player", "all_revealed", "mannerisms_revealed"
    )
    prior_trues = {f for f in _one_way_true_flags if merged.get(f)}

    # 2. Snapshot experience states
    existing_intercourse = merged.get("intercourse_experience") or "virgin"
    incoming_intercourse = incoming_app.get("intercourse_experience")
    existing_oral = merged.get("oral_experience", "inexperienced")
    incoming_oral = incoming_app.get("oral_experience")
    existing_manual = merged.get("manual_experience", "inexperienced")
    incoming_manual = incoming_app.get("manual_experience")

    # 3. Apply incoming data
    for k, v in incoming_app.items():
        if v is None:
            continue
        v_str = str(v).strip()
        if not v_str:
            continue

        if k in IMMUTABLE_PHYSICAL_APPEARANCE_KEYS:
            existing_val = merged.get(k)
            existing_str = str(existing_val or "").strip().lower()
            if not existing_val or existing_str in ("", "unknown", "none", "n/a", "null"):
                merged[k] = v
        elif k in (
            "intimate_demeanor", "demeanor",
            "intimate_dynamic", "dynamic",
            "erotic_openness", "openness",
            "turn_ons", "sensitive_spots", "erogenous_zones",
            "fetishes", "kinks",
            "act_likes", "favorite_acts", "preferred_acts",
            "act_dislikes", "disliked_acts"
        ):
            existing_val = merged.get(k)
            if not is_valid_persona_attribute_string(existing_val):
                if is_valid_persona_attribute_string(v):
                    merged[k] = v
        elif k in ("undergarments", "bra", "underwear"):
            existing_val = merged.get(k)
            if not existing_val or str(existing_val).strip().lower() in ("", "unknown", "none", "n/a", "null", "{}"):
                merged[k] = v
            elif isinstance(existing_val, dict) and isinstance(v, dict):
                for sub_k in ("bra", "underwear"):
                    if not existing_val.get(sub_k) and v.get(sub_k):
                        existing_val[sub_k] = v[sub_k]
        elif k == "intimate_memories":
            if isinstance(v, list) and v:
                existing_mems = merged.get("intimate_memories") or []
                combined_mems = list(existing_mems)
                for mem in v:
                    if mem not in combined_mems:
                        combined_mems.append(mem)
                merged["intimate_memories"] = combined_mems
            continue
        elif k in ("past_intimate_history", "past_intimate_entries"):
            if v and v != "[]" and v != []:
                merged[k] = v
            continue
        elif k in ("predetermined_intercourse", "intercourse_experience", "oral_experience", "manual_experience"):
            # Managed by experience ratchets below
            continue
        else:
            merged[k] = v

    # 4. Enforce experience progress ratchets with provenance guard
    mems = merged.get("intimate_memories") or incoming_app.get("intimate_memories") or []
    has_sex_mem = any(any(k in str(m).lower() for k in INTERCOURSE_MEMORY_KEYWORDS) for m in mems)
    has_oral_give = any(any(k in str(m).lower() for k in ORAL_GIVE_MEMORY_KEYWORDS) for m in mems)
    has_oral_rec = any(any(k in str(m).lower() for k in ORAL_RECEIVE_MEMORY_KEYWORDS) for m in mems)
    has_manual_give = any(any(k in str(m).lower() for k in MANUAL_GIVE_MEMORY_KEYWORDS) for m in mems)
    has_manual_rec = any(any(k in str(m).lower() for k in MANUAL_RECEIVE_MEMORY_KEYWORDS) for m in mems)
    had_first_time = bool(merged.get("had_first_time_with_player") or incoming_app.get("had_first_time_with_player"))

    existing_pred_i = str(existing_app.get("predetermined_intercourse") or "virgin").strip().lower()

    is_unanchored_procedural_regen = (
        existing_pred_i == "virgin" and
        (incoming_app.get("predetermined_intercourse") == "non_virgin") and
        not had_first_time and
        not has_sex_mem
    )

    if is_unanchored_procedural_regen:
        # Block rogue procedural generation from ratcheting an established canon virgin
        merged["predetermined_intercourse"] = "virgin"
        merged["intercourse_experience"] = "virgin"
        merged["oral_experience"] = existing_oral if existing_oral in ORAL_INTIMACY_STATES else "inexperienced"
        merged["manual_experience"] = existing_manual if existing_manual in MANUAL_INTIMACY_STATES else "inexperienced"
    else:
        # Live encounter or verified update
        if existing_pred_i == "virgin" and incoming_intercourse == "non_virgin":
            merged["had_first_time_with_player"] = True
        merged["intercourse_experience"] = merge_intercourse_states(existing_intercourse, incoming_intercourse)
        merged["oral_experience"] = merge_oral_states(existing_oral, incoming_oral)
        merged["manual_experience"] = merge_manual_states(existing_manual, incoming_manual)



    merged = enforce_intimacy_safeguard_invariants(merged)

    # 5. Restore one-way true flags
    for _flag in prior_trues:
        merged[_flag] = True

    return merged


from .logic import (
    infer_intimate_dynamic_from_traits, infer_erotic_openness_from_traits,
    enforce_intimacy_safeguard_invariants, merge_manual_states,
    infer_intimate_demeanor_from_traits, merge_intercourse_states,
    merge_oral_states, sanitize_sensitive_spots_for_species
)
from .generation import generate_dynamic_intimate_attributes
