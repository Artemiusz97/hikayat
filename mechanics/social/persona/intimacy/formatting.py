from __future__ import annotations
from .constants import *
import json
import hashlib
import re
from typing import Dict, Any, List, Optional
from ..core import *

def format_milestone_memory(event_type: str, npc_name: str, custom_summary: str = "") -> str:
    """Formats a concise, evocative memory journal entry for a romantic or intimate milestone."""
    if custom_summary and isinstance(custom_summary, str) and custom_summary.strip():
        s = custom_summary.strip().rstrip(".")
        # Capitalize nicely if lowercase start
        if s and s[0].islower():
            s = s[0].upper() + s[1:]
        return s

    ev = str(event_type or "").lower().strip()
    name = str(npc_name or "partner").strip()
    if ev == "intercourse":
        return f"Shared intimate night with {name}"
    elif ev == "oral_give":
        return f"Provided oral intimacy to {name}"
    elif ev == "oral_receive":
        return f"Received oral intimacy from {name}"
    elif ev == "manual_give":
        return f"Manually stimulated {name}"
    elif ev == "manual_receive":
        return f"Received manual stimulation from {name}"
    elif ev == "first_kiss":
        return f"Shared a passionate first kiss with {name}"
    elif ev == "kiss":
        return f"Shared a passionate kiss with {name}"
    elif ev == "confession":
        return f"Confessed feelings and agreed to date {name}"
    elif ev == "date":
        return f"Shared a romantic date and close moments with {name}"
    return f"Romantic milestone shared with {name}"

def format_dynamic_prompt_directive(partner_name: str, dynamic_val: str) -> str:
    """Formats an autonomous behavioral prompt directive for an NPC based on their intimate dynamic.
    Supports canonical templates as well as custom and dynamically generated dynamic strings.
    """
    if not dynamic_val:
        return ""
    d_low = dynamic_val.lower()

    # 1. Assertive & Dominant Initiative (Takes physical charge, top, corners/pins partner)
    if any(kw in d_low for kw in ("proactive", "dominant", "brat", "switch", "assertive", "forward", "lead", "aggressive", "seductress", "top", "in charge", "bossy", "take charge")):
        return (
            f"  * AUTONOMOUS PHYSICAL INITIATIVE ({partner_name} — Assertive/Dominant: {dynamic_val}): "
            f"In romantic, flirtatious, or intimate moments, THEY MAKE THE PHYSICAL MOVE FIRST "
            f"(e.g. stepping close into your personal space, pulling your collar/tie, pinning you against a wall/locker, cornering you, or initiating a kiss) without waiting for the player to ask! "
            f"Format next_choices as the player's active reactions/responses to what {partner_name} is actively doing to them."
        )

    # 2. Insatiable & Voracious Initiative (Demanding, hungry, uninhibited in private)
    if any(kw in d_low for kw in ("insatiable", "voracious", "high-drive", "relentless", "demanding", "hungry", "carnal", "greedy", "craving", "unquenchable")):
        return (
            f"  * AUTONOMOUS PHYSICAL INITIATIVE ({partner_name} — Insatiable & High-Drive: {dynamic_val}): "
            f"In private, romantic, or intimate settings, {partner_name}'s composure gives way to intense physical hunger. "
            f"{partner_name} AUTONOMOUSLY grabs, clings, pulls you close onto the bed/seat, or demands physical contact without waiting to be prompted! "
            f"They cannot keep their hands off the player. Format next_choices reacting to {partner_name}'s eager, physical hunger."
        )

    # 3. Attentive Service & Pampering Initiative (Focuses on partner's pleasure, pampering, worship)
    if any(kw in d_low for kw in ("service", "devoted", "attentive", "pamper", "pleasing", "worship", "worships", "worshipping", "dedicated")):
        return (
            f"  * AUTONOMOUS PHYSICAL INITIATIVE ({partner_name} — Service-Oriented & Pampering: {dynamic_val}): "
            f"In intimate or tender moments, {partner_name} AUTONOMOUSLY initiates pampering and devotion without being asked "
            f"(e.g. softly unbuttoning your jacket, massaging your shoulders/neck, kneeling to attend to your comfort, or kissing your hands). "
            f"Their peak pleasure comes from worshiping and satisfying you. Format next_choices as how the player receives or directs their attentive devotion."
        )

    # 4. Receptive & Yielding Surrender (Submissive, inviting bodily cues, guiding hands)
    if any(kw in d_low for kw in ("receptive", "yielding", "submissive", "surrender", "bottom", "obedient", "docile", "meek", "compliant")):
        return (
            f"  * AUTONOMOUS INTIMATE RESPONSE ({partner_name} — Receptive & Yielding: {dynamic_val}): "
            f"{partner_name} craves the player taking complete charge. In intimate moments, they AUTONOMOUSLY display inviting bodily surrender: "
            f"arching into the player's touch, guiding the player's hands to where they ache to be held, tilting their head to expose their neck, or shivering with breathless anticipation. "
            f"Format next_choices as the player leading and commanding the encounter."
        )

    # 5. Dynamic Fallback for Custom/LLM-generated strings
    return (
        f"  * AUTONOMOUS INTIMATE DYNAMIC ({partner_name}: {dynamic_val}): "
        f"In romantic, flirtatious, or intimate encounters, {partner_name} actively expresses their dynamic ({dynamic_val}) through characterful physical initiative and presence."
    )

def format_openness_prompt_directive(partner_name: str, openness_val: str) -> str:
    """Formats an erotic openness prompt directive for an NPC based on their openness tier."""
    if not openness_val:
        return ""
    o_low = openness_val.lower()
    if "prude" in o_low or "modest" in o_low:
        return (
            f"  * EROTIC OPENNESS ({partner_name}: Prude / Modest): High modesty barrier. "
            f"Never initiate unsolicited dirty talk; flustered, blushing, or defensive around crude talk. Requires deep trust/romance."
        )
    elif "shameless" in o_low or "lewd" in o_low:
        return (
            f"  * EROTIC OPENNESS ({partner_name}: Shameless / Lewd): Hedonistic high-drive; "
            f"zero verbal filter; openly speaks dirty, craves erotic contact, and teases with shameless, provocative audacity."
        )
    elif "bold" in o_low or "uninhibited" in o_low:
        return (
            f"  * EROTIC OPENNESS ({partner_name}: Bold / Uninhibited): Sex-positive; "
            f"comfortable with suggestive innuendos, touch, and flirtatious banter without shame."
        )
    else:
        return (
            f"  * EROTIC OPENNESS ({partner_name}: Reserved / Moderate): Balanced intimacy; "
            f"natural pacing; comfortable with private romance and passion, but values timing and mutual comfort."
        )

def format_turn_ons_prompt_directive(partner_name: str, turn_ons_val: str, dynamic_val: str = "") -> str:
    """Formats a behavioral prompt directive for NPC turn-ons and reactive guidance."""
    if not turn_ons_val or str(turn_ons_val).lower() in ("none", "unknown", ""):
        return ""
    d_low = str(dynamic_val or "").lower()
    is_proactive = any(kw in d_low for kw in ("proactive", "dominant", "brat", "switch", "assertive", "forward", "lead", "seductress", "insatiable", "high-drive"))

    if is_proactive:
        action_guide = (
            f"THEY AUTONOMOUSLY LEAD AND GUIDE: {partner_name} actively guides the player's hands or lips directly to their turn-ons "
            f"({turn_ons_val}) or demands/initiates the favored actions without hesitation!"
        )
    else:
        action_guide = (
            f"THEY WARMLY SURRENDER AND REACT: {partner_name} shivers, arches, gasps, and reacts with intense warmth and breathlessness "
            f"when the player touches their turn-on spots or performs their favored actions ({turn_ons_val})."
        )

    return (
        f"  * INTIMATE TURN-ONS ({partner_name}): {turn_ons_val}.\n"
        f"    - {action_guide}\n"
        f"    - Choices targeting these triggers grant lower difficulty checks and deeper emotional/physical bonding."
    )

def format_fetish_prompt_directive(partner_name: str, fetish_val: str, dynamic_val: str = "") -> str:
    """Formats a fetish priority prompt directive when an NPC has an active kink."""
    if not fetish_val or str(fetish_val).lower() in ("none", "none (vanilla)", "unknown", ""):
        return ""

    return (
        f"  * FETISH PRIORITY DIRECTIVE ({partner_name} — Active Kink: {fetish_val}):\n"
        f"    - In private or bedroom scenes, {partner_name} will AUTONOMOUSLY ATTEMPT TO FULFILL THEIR FETISH FIRST "
        f"(e.g. introducing props, whispering kink desires, or initiating thematic play).\n"
        f"    - next_choices MUST offer choices to indulge their fetish (high affinity surge) or gently decline/negotiate."
    )

def format_act_preferences_prompt_directive(partner_name: str, likes_val: str = "", dislikes_val: str = "", dynamic_val: str = "") -> str:
    """Formats behavioral rules for liked and disliked intimate acts."""
    lines = []
    d_low = str(dynamic_val or "").lower()
    is_proactive = any(kw in d_low for kw in ("proactive", "dominant", "brat", "switch", "assertive", "forward", "lead", "seductress", "insatiable", "high-drive"))

    if likes_val and str(likes_val).lower() not in ("none", "unknown", ""):
        if is_proactive:
            like_desc = f"AUTONOMOUSLY initiates or eagerly steers the encounter into their preferred acts ({likes_val})"
        else:
            like_desc = f"welcomes without hesitation and reacts passionately when the player initiates their preferred acts ({likes_val})"
        lines.append(f"    - PREFERRED ACTS ({likes_val}): {partner_name} {like_desc}.")

    if dislikes_val and str(dislikes_val).lower() not in ("none", "unknown", ""):
        lines.append(
            f"    - DISLIKED ACTS ({dislikes_val}): {partner_name} AVOIDS these acts. "
            f"If asked by the player, they will hesitate/reluctantly comply on check success (-1 affinity) or firmly refuse on failure."
        )

    if not lines:
        return ""
    return f"  * INTIMATE ACT & POSITION PREFERENCES ({partner_name}):\n" + "\n".join(lines)

def format_intimate_profile_sections(app_dict: Dict[str, Any], gender: str = "", race: str = "human", scen_key: str = "fantasy", info_level: int = 1, revealed_flags: Dict[str, Any] = None) -> Dict[str, Any]:
    """Formats intimate profile categorized sections (Anatomy & Experience, Demeanor & Dynamic, Turn-Ons & Desires, Act Preferences) with discovery metadata."""
    app_dict = enforce_intimacy_safeguard_invariants(dict(app_dict or {}))
    revealed_flags = revealed_flags or {}
    intimate_unlocked = (info_level >= 3) or revealed_flags.get("intimate_revealed", False) or revealed_flags.get("all_revealed", False) or app_dict.get("intimate_revealed", False)

    raw_g = gender.strip().lower()
    is_male = any(kw in raw_g for kw in ("male", "man", "boy", "lord", "he", "him", "his")) and not any(kw in raw_g for kw in ("female", "woman"))
    is_female = not is_male

    b_size = app_dict.get("breast_size")
    p_size = app_dict.get("penis_size")

    anatomy_lines = []
    discovered = {}

    # 1. Size
    if is_female:
        if (intimate_unlocked or info_level >= 3) and b_size:
            anatomy_lines.append(f"• **Breast Size**: {b_size.title()}")
            discovered["size"] = b_size.title()
        else:
            anatomy_lines.append("• **Breast Size**: *Unknown*")
    elif is_male:
        if (intimate_unlocked or info_level >= 3) and p_size:
            anatomy_lines.append(f"• **Penis Size**: {p_size.title()}")
            discovered["size"] = p_size.title()
        else:
            anatomy_lines.append("• **Penis Size**: *Unknown*")
    else:
        if intimate_unlocked or info_level >= 3:
            if b_size:
                anatomy_lines.append(f"• **Breast Size**: {b_size.title()}")
                discovered["size"] = b_size.title()
            if p_size:
                anatomy_lines.append(f"• **Penis Size**: {p_size.title()}")
                discovered["penis_size"] = p_size.title()
        else:
            anatomy_lines.append("• **Breast Size**: *Unknown*")
            anatomy_lines.append("• **Penis Size**: *Unknown*")

    # 2. Intercourse Track
    intercourse = app_dict.get("intercourse_experience") or app_dict.get("predetermined_intercourse") or "virgin"

    intercourse_revealed = intimate_unlocked or revealed_flags.get("intercourse_revealed", False) or app_dict.get("intercourse_revealed", False)

    if intercourse_revealed and intercourse != "unknown":
        i_disp = "Virgin" if intercourse == "virgin" else "Non-Virgin"
        anatomy_lines.append(f"• **Intercourse**: {i_disp}")
        discovered["intercourse"] = i_disp
    else:
        anatomy_lines.append("• **Intercourse**: *Unknown*")

    # 3. Oral Intimacy Track
    oral = app_dict.get("oral_experience", "unknown")
    oral_revealed = intimate_unlocked or revealed_flags.get("oral_revealed", False) or app_dict.get("oral_revealed", False) or intercourse_revealed
    if oral_revealed and oral != "unknown":
        oral_map = {
            "inexperienced": "Inexperienced",
            "has_done_oral": "Has Performed",
            "has_received_oral": "Has Received",
            "has_done_and_received_oral": "Has Performed & Received"
        }
        o_disp = oral_map.get(oral, "Inexperienced")
        anatomy_lines.append(f"• **Oral Intimacy**: {o_disp}")
        discovered["oral"] = o_disp
    else:
        anatomy_lines.append("• **Oral Intimacy**: *Unknown*")

    # 4. Manual Intimacy Track
    manual = app_dict.get("manual_experience", "unknown")
    manual_revealed = intimate_unlocked or revealed_flags.get("manual_revealed", False) or app_dict.get("manual_revealed", False) or intercourse_revealed
    if manual_revealed and manual != "unknown":
        man_map = {
            "inexperienced": "Inexperienced",
            "has_done_manual": "Has Given",
            "has_received_manual": "Has Received",
            "has_done_and_received_manual": "Has Given & Received"
        }
        m_disp = man_map.get(manual, "Inexperienced")
        anatomy_lines.append(f"• **Manual Intimacy**: {m_disp}")
        discovered["manual"] = m_disp
    else:
        anatomy_lines.append("• **Manual Intimacy**: *Unknown*")

    # Demeanor & Dynamic Section
    dynamic_lines = []
    demeanor = app_dict.get("intimate_demeanor")
    if not is_valid_persona_attribute_string(demeanor):
        demeanor = None
    demeanor_revealed = intimate_unlocked or revealed_flags.get("demeanor_revealed", False) or app_dict.get("demeanor_revealed", False)
    if demeanor_revealed and demeanor:
        dynamic_lines.append(f"• **Demeanor**: {demeanor}")
        discovered["demeanor"] = demeanor
    else:
        dynamic_lines.append("• **Demeanor**: *Unknown*")

    dynamic = app_dict.get("intimate_dynamic") or app_dict.get("dynamic")
    if not is_valid_persona_attribute_string(dynamic):
        dynamic = None
    dynamic_revealed = intimate_unlocked or revealed_flags.get("dynamic_revealed", False) or app_dict.get("dynamic_revealed", False) or demeanor_revealed
    if dynamic_revealed and dynamic:
        dynamic_lines.append(f"• **Dynamic**: {dynamic}")
        discovered["dynamic"] = dynamic
    else:
        dynamic_lines.append("• **Dynamic**: *Unknown*")

    openness = app_dict.get("erotic_openness") or app_dict.get("openness")
    if not is_valid_persona_attribute_string(openness):
        openness = None
    openness_revealed = intimate_unlocked or revealed_flags.get("openness_revealed", False) or app_dict.get("openness_revealed", False) or dynamic_revealed
    if openness_revealed and openness:
        open_label = get_erotic_openness_label(openness)
        dynamic_lines.append(f"• **Openness**: {open_label}")
        discovered["openness"] = open_label
    else:
        dynamic_lines.append("• **Openness**: *Unknown*")

    # Turn-Ons & Desires Section
    sensitivity_lines = []
    turn_ons = clean_attribute_list_string(app_dict.get("turn_ons"))
    sensitive_spots = clean_attribute_list_string(app_dict.get("sensitive_spots"))
    if not turn_ons and sensitive_spots:
        turn_ons = sensitive_spots
    if not sensitive_spots and turn_ons:
        sensitive_spots = turn_ons

    turns_revealed = intimate_unlocked or revealed_flags.get("turn_ons_revealed", False) or revealed_flags.get("sensitive_spots_revealed", False) or app_dict.get("turn_ons_revealed", False) or app_dict.get("sensitive_spots_revealed", False)
    if turns_revealed and (turn_ons or sensitive_spots):
        s_val = sensitive_spots if sensitive_spots and sensitive_spots.lower() != 'none' else (turn_ons if turn_ons and turn_ons.lower() != 'none' else 'None')
        t_raw = turn_ons if turn_ons and turn_ons.lower() != 'none' else (sensitive_spots if sensitive_spots and sensitive_spots.lower() != 'none' else 'None')
        t_val = tag_turn_on_items(t_raw, race=race) if t_raw != 'None' else 'None'
        if s_val != 'None':
            sensitivity_lines.append(f"• **Sensitive Spots**: {s_val}")
        sensitivity_lines.append(f"• **Turn-Ons**: {t_val}")
        if t_val != 'None':
            discovered["turn_ons"] = t_val
        if s_val != 'None':
            discovered["sensitive_spots"] = s_val
    else:
        sensitivity_lines.append("• **Sensitive Spots**: *Unknown*")
        sensitivity_lines.append("• **Turn-Ons**: *Unknown*")

    fetishes = clean_attribute_list_string(app_dict.get("fetishes"))
    fetish_revealed = intimate_unlocked or revealed_flags.get("fetishes_revealed", False) or app_dict.get("fetishes_revealed", False)
    if fetish_revealed and fetishes:
        f_val = fetishes if fetishes.lower() not in ('none', 'none (vanilla)') else 'None (Vanilla)'
        sensitivity_lines.append(f"• **Fetishes & Kinks**: {f_val}")
        if f_val not in ('None', 'None (Vanilla)'):
            discovered["fetishes"] = f_val
    else:
        sensitivity_lines.append("• **Fetishes & Kinks**: *Unknown*")

    # Act & Position Preferences Section
    act_lines = []
    act_likes = clean_attribute_list_string(app_dict.get("act_likes"))
    act_dislikes = clean_attribute_list_string(app_dict.get("act_dislikes"))
    act_revealed = intimate_unlocked or revealed_flags.get("act_preferences_revealed", False) or app_dict.get("act_preferences_revealed", False)

    if act_revealed and (act_likes or act_dislikes):
        l_val = act_likes if act_likes else 'None'
        d_val = act_dislikes if act_dislikes else 'None'
        act_lines.append(f"• **Preferred / Likes**: {l_val}")
        act_lines.append(f"• **Aversions / Dislikes**: {d_val}")
        if l_val != 'None':
            discovered["act_likes"] = l_val
        if d_val != 'None':
            discovered["act_dislikes"] = d_val
    else:
        act_lines.append("• **Preferred / Likes**: *Unknown*")
        act_lines.append("• **Aversions / Dislikes**: *Unknown*")

    # Undergarments Section
    undergarment_lines = []
    under_dict = app_dict.get("undergarments")
    if not isinstance(under_dict, dict):
        if app_dict.get("bra") or app_dict.get("underwear"):
            under_dict = {
                "bra": str(app_dict.get("bra", "")).strip(),
                "underwear": str(app_dict.get("underwear", "")).strip()
            }
        else:
            under_dict = generate_procedural_undergarments(
                seed_str=gender + "_" + race,
                gender=gender,
                openness=app_dict.get("erotic_openness") or app_dict.get("openness", "moderate"),
                dynamic=app_dict.get("intimate_dynamic") or app_dict.get("dynamic", ""),
                traits=app_dict.get("traits") or []
            )

    underwear_revealed = (
        intimate_unlocked
        or revealed_flags.get("underwear_revealed", False)
        or revealed_flags.get("all_revealed", False)
        or app_dict.get("underwear_revealed", False)
        or app_dict.get("intimate_revealed", False)
    )

    bra_val = under_dict.get("bra", "")
    und_val = under_dict.get("underwear", "")

    if is_female:
        if (underwear_revealed or info_level >= 3) and (bra_val or und_val):
            undergarment_lines.append(f"• **Bra**: {bra_val or 'None (Bra-less)'}")
            undergarment_lines.append(f"• **Underwear**: {und_val or 'None (Commando)'}")
            discovered["bra"] = bra_val or "None (Bra-less)"
            discovered["underwear"] = und_val or "None (Commando)"
        else:
            undergarment_lines.append("• **Bra**: *Unknown*")
            undergarment_lines.append("• **Underwear**: *Unknown*")
    else:
        if (underwear_revealed or info_level >= 3) and und_val:
            undergarment_lines.append(f"• **Underwear**: {und_val}")
            discovered["underwear"] = und_val
        else:
            undergarment_lines.append("• **Underwear**: *Unknown*")

    return {
        "anatomy": anatomy_lines,
        "dynamic": dynamic_lines,
        "undergarments": undergarment_lines,
        "sensitivities": sensitivity_lines,
        "act_preferences": act_lines,
        "discovered": discovered
    }

def format_intimate_profile_lines(app_dict: Dict[str, Any], gender: str = "", race: str = "human", scen_key: str = "fantasy", info_level: int = 1, revealed_flags: Dict[str, Any] = None) -> List[str]:
    """Formats intimate profile bullet points (Anatomy & Experience, Demeanor, Dynamic, Undergarments, Turn-Ons, Fetishes, Act Preferences)."""
    sec = format_intimate_profile_sections(
        app_dict, gender=gender, race=race, scen_key=scen_key,
        info_level=info_level, revealed_flags=revealed_flags
    )
    return sec["anatomy"] + sec["dynamic"] + sec["undergarments"] + sec["sensitivities"] + sec["act_preferences"]

def format_persona_embed_fields(app_dict: Dict[str, Any], gender: str = "", race: str = "human", scen_key: str = "fantasy", desc: Any = "", mannerisms: str = "", traits: List[str] = None, info_level: int = 1, revealed_flags: Dict[str, Any] = None, include_intimate: bool = True) -> List[Dict[str, str]]:
    """Formats fields for Discord /contacts profile embeds (Appearance, NSFW Intimate Profile, Mannerisms, 3-4 Traits)."""
    app_dict = normalize_appearance(app_dict or {}, gender=gender, race=race, scen_key=scen_key, desc=desc, traits=traits)
    revealed_flags = revealed_flags or {}
    intimate_unlocked = (info_level >= 3) or revealed_flags.get("intimate_revealed", False) or revealed_flags.get("all_revealed", False) or app_dict.get("intimate_revealed", False)

    eye = (app_dict.get("eye_color") or "Unknown").replace("_", " ").title()
    h_color = (app_dict.get("hair_color") or "Unknown").title()
    h_len = (app_dict.get("hair_length") or "").title()
    h_style = (app_dict.get("hair_style") or "").title()
    stature = (app_dict.get("stature") or "Average").title()
    physique = (app_dict.get("physique") or "").title()

    is_dyed = bool(app_dict.get("is_dyed"))
    coat_val = app_dict.get("coat_color")
    if not is_dyed and coat_val and is_contrasting_shade(coat_val, h_color):
        is_dyed = True

    natural_hair = app_dict.get("natural_hair_color")
    if is_dyed and not natural_hair and coat_val:
        natural_hair = infer_natural_hair_color_from_coat(coat_val, race)

    if is_dyed and natural_hair and natural_hair.lower() != h_color.lower():
        hair_display = f"{h_len} {h_style} {h_color} (Dyed; Natural: {natural_hair.title()})".strip()
    else:
        hair_display = f"{h_len} {h_style} {h_color}".strip()

    app_lines = [
        f"• **Eyes**: {eye}",
        f"• **Hair**: {hair_display}",
        f"• **Stature**: {stature}"
    ]
    if physique:
        app_lines.append(f"• **Physique**: {physique}")

    coat = app_dict.get("coat_color")
    skin = app_dict.get("skin_color")
    skin_type = app_dict.get("skin_type")

    is_half = is_half_beast_race(race)

    if not is_half and coat:
        coat_lower = coat.lower()
        if "scale" in coat_lower or skin_type == "scaly" or is_scaly_race(race):
            app_lines.append(f"• **Scales**: {coat.title()}")
        elif "fur" in coat_lower or skin_type == "furry":
            app_lines.append(f"• **Fur / Coat**: {coat.title()}")
        elif "feather" in coat_lower or skin_type == "feathered":
            app_lines.append(f"• **Feathers**: {coat.title()}")
        else:
            app_lines.append(f"• **Coat**: {coat.title()}")
    elif skin:
        app_lines.append(f"• **Skin Color**: {skin.title()}")

    features = app_dict.get("distinctive_features")
    if features:
        if is_half:
            app_lines.append(f"• **Hybrid Features**: {features.title()}")
        else:
            app_lines.append(f"• **Features**: {features.title()}")

    outfit = app_dict.get("outfit_style")
    if outfit:
        app_lines.append(f"• **Outfit**: {outfit.title()}")

    fields = [{
        "name": "✨ Physical Appearance",
        "value": "\n".join(app_lines),
        "inline": False
    }]

    if include_intimate and is_nsfw_scenario(scen_key):
        nsfw_lines = format_intimate_profile_lines(
            app_dict, gender=gender, race=race, scen_key=scen_key,
            info_level=info_level, revealed_flags=revealed_flags
        )
        fields.append({
            "name": "🔞 Intimate Profile",
            "value": "\n".join(nsfw_lines),
            "inline": False
        })

    mannerisms_revealed = (info_level >= 2) or revealed_flags.get("mannerisms_revealed", False) or app_dict.get("mannerisms_revealed", False)
    mannerisms_list = format_mannerisms_list(mannerisms, race=race, desc=desc, traits=traits)

    if mannerisms_revealed and mannerisms_list:
        val = "\n".join(f"• {m}" for m in mannerisms_list[:3])
        fields.append({
            "name": "🎭 Mannerisms & Habits",
            "value": val,
            "inline": False
        })
    else:
        fields.append({
            "name": "🎭 Mannerisms & Habits",
            "value": "• *Not yet observed*",
            "inline": False
        })

    return fields


from .generation import tag_turn_on_items

from .appearance import normalize_appearance
from .logic import get_erotic_openness_label, enforce_intimacy_safeguard_invariants
