"""
mechanics/social/persona/actor_card.py — Unified Actor Direction Card Builder
=============================================================================
Synthesizes present NPC persona state (from contacts, lorebook, and memory)
into an authoritative, situational Actor Direction Card for the narrative LLM.

Implements 3-Tier Situational Persona Gating:
  - Layer 1: Everyday Social (Default)
      Physical appearance, voice tone, core motivation, grounded in-room activity,
      categorized mannerisms with turn cooldown, immediate agenda, friction & boundaries,
      social surface of erotic openness, relational memory/open thread.
      *Strictly gates out explicit anatomy, undergarments, sensitive spots, and climax rules.*
  - Layer 2: Romantic Tension / Flirtation (Active on flirt, romantic track, affinity >= 100, date)
      Intimate demeanor, dynamic preview, surface turn-ons/turn-offs, dating/virginity canon.
  - Layer 3: Active Intimacy / Erotic Scene (Active in erotic dialogue or undress)
      Undergarments, anatomy pride/insecurity directives, sensitive spots, kinks/fetishes,
      act preferences, intimate experience canon, excitement meter and climax rules.
"""
from __future__ import annotations
from typing import Dict, Any, List, Tuple, Optional
import hashlib
import re

from mechanics.social.persona.core import (
    categorize_likes_and_dislikes,
    format_mannerisms_list,
    is_nsfw_scenario,
    is_contrasting_shade,
    infer_natural_hair_color_from_coat,
)
from mechanics.social.races import format_race_display
from mechanics.combat.traits import format_trait_behavioral_prompt
from mechanics.social.persona.intimacy.formatting import (
    format_demeanor_prompt_directive,
    format_dynamic_prompt_directive,
    format_turn_ons_prompt_directive,
    format_desires_and_turn_offs_prompt_directive,
    format_fetish_prompt_directive,
    format_act_preferences_prompt_directive,
    format_body_asset_narrative_directive,
    format_openness_prompt_directive,
    format_stature_and_physique_narrative_directive,
)
from mechanics.social.persona.intimacy.logic import (
    sanitize_sensitive_spots_for_species,
    get_erotic_openness_label,
)
from mechanics.social.persona.intimacy.appearance import clean_attribute_list_string
from mechanics.social.relationships import get_unlocked_info_level
from mechanics.world.schedules import (
    get_time_block_key,
    is_schedule_transition_imminent,
    get_npc_scheduled_location,
)


def derive_scene_activity(
    npc: Dict[str, Any],
    location: str = "",
    current_minute: int = 480,
    scen_key: str = "fantasy",
) -> str:
    """
    Derives a realistic, grounded in-room physical activity for an NPC present in the room.
    Combines role, club, location, time-of-day, and preferences (likes/dislikes).
    """
    if not isinstance(npc, dict):
        return "Observing the surroundings attentively"

    name = str(npc.get("name") or "Character").strip()
    basic = npc.get("basic_info") or {}
    role = str(npc.get("role") or basic.get("role") or npc.get("occupation") or "").lower()
    club = str(npc.get("club") or basic.get("club") or "").lower()
    loc_lower = str(location or "").lower()
    prefs = npc.get("preferences") or []
    traits = npc.get("unlocked_traits") or npc.get("traits") or basic.get("traits") or []

    likes, dislikes = categorize_likes_and_dislikes(
        prefs, traits=traits, role=role, race=npc.get("race", ""), desc=basic.get("description", "")
    )

    clean_likes = [re.sub(r'^(likes?|prefers?|loves?|enjoys?)\s+', '', l, flags=re.IGNORECASE).strip() for l in likes]
    clean_dislikes = [re.sub(r'^(dislikes?|hates?|averse to)\s+', '', d, flags=re.IGNORECASE).strip() for d in dislikes]

    time_block = get_time_block_key(current_minute)
    seed = int(hashlib.md5(f"{name}_{location}_{time_block}".encode("utf-8")).hexdigest(), 16)

    # 1. Location-specific activities
    if any(k in loc_lower for k in ("library", "study", "archive", "book")):
        liked_subj = clean_likes[0] if clean_likes else "history"
        return f"Sitting at a quiet table with a notebook open, researching {liked_subj.lower()}"
    elif any(k in loc_lower for k in ("cafeteria", "canteen", "dining")):
        food = clean_likes[0] if clean_likes else "a warm beverage"
        return f"Eating at a dining table, enjoying {food.lower()} while people-watching"
    elif any(k in loc_lower for k in ("gym", "pool", "dojo", "athletic", "field", "training")):
        if "swim" in club:
            return "Standing near the lane edge in training swimwear, drying hair with a towel"
        elif any(c in club for c in ("kendo", "martial")):
            return "Wiping down wooden training gear while catching breath from practice drills"
        else:
            return "Finishing stretching routines, adjusting athletic gear with focused energy"
    elif any(k in loc_lower for k in ("lab", "science", "chemistry", "alchemy")):
        return "Organizing glass beakers and carefully labeling observation logs on the workbench"
    elif any(k in loc_lower for k in ("music", "piano", "art", "studio")):
        return "Quietly tuning an instrument while humming a melodic rhythm"
    elif any(k in loc_lower for k in ("tavern", "inn", "pub", "bar")):
        bev = clean_likes[0] if clean_likes else "cider"
        return f"Leaning against the corner booth, sipping {bev.lower()} and watching the crowd"
    elif any(k in loc_lower for k in ("courtyard", "fountain", "garden", "grounds")):
        if any(d in " ".join(clean_dislikes).lower() for d in ("crowd", "noise")):
            return "Sitting on a secluded stone bench beneath tree shade, avoiding the busy foot traffic"
        return "Leaning near the fountain wall, enjoying the fresh air and ambient chatter"
    elif any(k in loc_lower for k in ("classroom", "homeroom")):
        if time_block == "commute":
            return "Setting down their school bag at their desk and chatting with classmates before the 08:00 AM homeroom bell"
        elif time_block in ("morning", "class_afternoon"):
            return "Organizing stationery at their desk and reviewing lecture notes between class periods"
        elif time_block == "lunch":
            return "Sitting at their desk, unpacking lunch while chatting with adjacent classmates"
        elif time_block in ("afternoon", "extracurricular", "evening"):
            return "Packing textbooks into a backpack while stretching after the final class bell"
        else:
            return "Gazing pensively out the window, spinning a pen between fingers"

    # 2. Preference-driven fallback
    if clean_likes:
        fav = clean_likes[seed % len(clean_likes)]
        return f"Occupied with thoughts of {fav.lower()}, idly adjusting personal belongings"

    # 3. Default role-based fallback
    if "teacher" in role or "staff" in role:
        return "Reviewing attendance rosters and grading sheets with a focused expression"
    elif "guard" in role or "knight" in role:
        return "Standing at a measured posture, surveying the room with watchful discipline"
    elif "merchant" in role:
        return "Straightening merchandise displays and balancing a ledger with quick tallies"

    return "Resting comfortably in the room, taking in the surroundings at an easy pace"


def derive_initial_micro_blocking(
    npc: Dict[str, Any],
    current_location: str = "",
    time_slot: str = "morning",
    stage_role: str = "room_bystander",
) -> Dict[str, str]:
    """
    Derives deterministic initial physical micro-blocking (spot, posture, active prop, prop focus, proximity)
    for an NPC staged in a room.
    """
    if not isinstance(npc, dict):
        return {
            "spot_and_posture": "standing attentively near the room entrance",
            "active_prop": "a personal satchel",
            "prop_focus": "paused_attentive" if stage_role in ("active_partner", "party_companion") else "absorbed",
            "proximity": "side_by_side" if stage_role == "party_companion" else ("conversational_distance" if stage_role == "active_partner" else "across_room"),
        }

    basic = npc.get("basic_info") or {}
    role = str(npc.get("role") or basic.get("role") or npc.get("occupation") or "").lower()
    club = str(npc.get("club") or basic.get("club") or "").lower()
    loc_lower = str(current_location or "").lower()
    prefs = npc.get("preferences") or []
    traits = npc.get("unlocked_traits") or npc.get("traits") or basic.get("traits") or []
    likes, _ = categorize_likes_and_dislikes(prefs, traits=traits, role=role, race=npc.get("race", ""), desc=basic.get("description", ""))
    clean_likes = [re.sub(r'^(likes?|prefers?|loves?|enjoys?)\s+', '', l, flags=re.IGNORECASE).strip() for l in likes]

    # 1. Proximity and focus based on stage role
    if stage_role == "party_companion":
        prox = "side_by_side"
        focus = "paused_attentive"
    elif stage_role == "active_partner":
        prox = "conversational_distance"
        focus = "paused_attentive"
    else:
        prox = "across_room"
        focus = "absorbed"

    # 2. Location-grounded spots and props
    if any(k in loc_lower for k in ("library", "study", "archive", "book")):
        spot = "seated at a wooden study table"
        prop = f"a reference book on {(clean_likes[0] if clean_likes else 'history').lower()} and an open notebook"
    elif any(k in loc_lower for k in ("cafeteria", "canteen", "dining")):
        spot = "seated at a dining booth"
        prop = f"a tray with {(clean_likes[0] if clean_likes else 'a warm snack').lower()} and an iced drink"
    elif any(k in loc_lower for k in ("gym", "pool", "dojo", "athletic", "field")):
        if "swim" in club:
            spot = "standing near the tiled lane edge"
            prop = "a sports towel and water bottle"
        else:
            spot = "resting on the wooden equipment bench"
            prop = "training gear and a water bottle"
    elif any(k in loc_lower for k in ("lab", "science", "chemistry", "alchemy")):
        spot = "standing at the chemical workstation"
        prop = "glass test beakers and a clipboard log"
    elif any(k in loc_lower for k in ("music", "piano", "art", "studio")):
        spot = "perched on the studio stool"
        prop = "an acoustic instrument and sheet music"
    elif any(k in loc_lower for k in ("tavern", "inn", "pub", "bar")):
        spot = "leaning against the polished counter"
        prop = f"a flagon of {(clean_likes[0] if clean_likes else 'cider').lower()}"
    elif any(k in loc_lower for k in ("courtyard", "fountain", "garden", "grounds")):
        spot = "leaning against the carved stone railing"
        prop = "a lightweight jacket and personal bag"
    elif any(k in loc_lower for k in ("classroom", "homeroom")):
        spot = "seated behind an orderly school desk"
        prop = "a student planner and a brass ballpoint pen"
    elif "teacher" in role or "staff" in role:
        spot = "standing behind the main desk"
        prop = "a stack of administrative rosters"
    elif "guard" in role or "knight" in role:
        spot = "standing at a measured stance near the doorway"
        prop = "a ceremonial side-blade"
    elif "merchant" in role:
        spot = "standing behind the merchandise counter"
        prop = "a wooden transaction ledger"
    else:
        spot = "leaning against the room wall"
        prop = "a small personal notebook"

    return {
        "spot_and_posture": spot,
        "active_prop": prop,
        "prop_focus": focus,
        "proximity": prox,
    }


def format_mannerisms_categorized(
    mannerisms_raw: Any,
    traits: list = None,
    role: str = "",
    race: str = "",
    desc: str = "",
    history_text: str = "",
) -> Dict[str, List[str]]:
    """
    Parses and categorizes behavioral mannerisms into:
      - 'idle': Baseline habit / resting tic
      - 'guarded': Stressed / defensive tell
      - 'warm': Flustered / affectionate / pleased tell
    Applies a repetition cooldown: if a tell appeared in the previous turn narrative,
    it is tagged with '[Used last turn — vary body language this turn]'.
    """
    raw_list = format_mannerisms_list(
        mannerisms_raw, race=race, desc=desc, traits=traits, role=role
    )

    categorized: Dict[str, List[str]] = {
        "idle": [],
        "guarded": [],
        "warm": [],
    }

    guarded_kws = (
        "nervous", "scowl", "challenged", "impatient", "crosses arms", "cross arm",
        "frown", "defensive", "tighten", "stare", "glare", "tilt back", "wary",
        "suspicious", "flustered", "clench", "avoid eye contact", "fidget",
        "bite", "sigh", "guard", "taps finger", "scowls", "sharp breath",
    )
    warm_kws = (
        "smiles", "pleased", "excited", "warm", "gentle", "soft", "swishes",
        "wags", "playful", "leaning", "lean in", "tail curl", "purr", "tuck hair",
        "chuckle", "soften", "ear twitch", "twitches ear", "eyes sparkle",
    )

    hist_lower = str(history_text or "").lower()

    for m in raw_list:
        m_str = str(m).strip()
        if not m_str:
            continue
        m_low = m_str.lower()

        # Categorize
        if any(kw in m_low for kw in guarded_kws):
            cat = "guarded"
        elif any(kw in m_low for kw in warm_kws):
            cat = "warm"
        else:
            cat = "idle"

        # Repetition cooldown check against previous turn narrative
        words = [w for w in re.findall(r'\b[a-z]{3,}\b', m_low) if w not in ("when", "while", "with", "that", "this")]
        was_used = False
        if len(words) >= 2 and hist_lower:
            for i in range(len(words) - 1):
                phrase = f"{words[i]} {words[i+1]}"
                if phrase in hist_lower:
                    was_used = True
                    break

        item_str = m_str
        if was_used:
            item_str += " [Used last turn — vary body language this turn]"

        categorized[cat].append(item_str)

    if not categorized["idle"] and not categorized["guarded"] and not categorized["warm"]:
        categorized["idle"].append("Speaks in a quiet, measured tone")

    return categorized


def derive_immediate_agenda(
    npc: Dict[str, Any],
    session: Dict[str, Any] = None,
    actions: List[Any] = None,
) -> str:
    """
    Generates a 1-sentence active conversational goal or upcoming schedule departure.
    Ensures the NPC has agency and does not wait passively.
    """
    if not isinstance(npc, dict):
        return "Engaging politely with the conversation at hand."

    name = str(npc.get("name") or "Character").strip()
    basic = npc.get("basic_info") or {}
    scen_key = (session or {}).get("scenario", "fantasy")
    current_minute = (session or {}).get("current_minute", 480)
    current_day = (session or {}).get("current_day", 1)

    # 1. Imminent schedule transition
    is_imminent, cur_block, next_block, mins_left = is_schedule_transition_imminent(
        current_minute, window_minutes=20, current_day=current_day, scen_key=scen_key
    )
    if is_imminent and next_block:
        sched_loc = get_npc_scheduled_location(
            npc, current_minute=current_minute + mins_left, current_day=current_day,
            scen_key=scen_key, time_slot=next_block, session_id=(session or {}).get("id")
        )
        dest_name = sched_loc.split("➔")[-1].strip() if "➔" in sched_loc else sched_loc
        block_display = next_block.replace("_", " ").capitalize()
        return f"Needs to wrap up within {mins_left} minutes to head to {dest_name} for {block_display} commitments."

    # 2. Unresolved open relational thread
    open_thread = str(npc.get("open_thread") or basic.get("open_thread") or "").strip()
    if open_thread:
        return f"Eager to follow up on the unresolved matter: '{open_thread}'."

    # 3. Pending appointment with player
    session_id = (session or {}).get("id")
    if session_id:
        try:
            import db
            appts = db.get_active_rendezvous_appointments(session_id)
            for ap in appts:
                if ap.get("npc_name", "").lower() == name.lower():
                    appt_loc = ap.get("rendezvous_location", "the agreed venue")
                    return f"Wants to confirm arrangements for meeting at {appt_loc}."
        except Exception:
            pass

    # 4. Explicit goal / motivation in lorebook or contact
    current_goal = str(npc.get("current_goal") or basic.get("current_goal") or npc.get("motivation") or basic.get("motivation") or "").strip()
    if current_goal and current_goal.lower() not in ("none", "unknown"):
        return f"Currently pursuing personal goal: {current_goal}."

    # 5. Role-based fallback
    role = str(npc.get("role") or basic.get("role") or "").lower()
    if "student" in role:
        return "Hoping to make good progress on daily tasks before the next period."
    elif "teacher" in role or "staff" in role:
        return "Managing schedule duties while attending to student inquiries."
    elif "merchant" in role:
        return "Interested in making a mutually beneficial deal or trade."

    return "Conversing naturally while remaining mindful of their daily responsibilities."


def format_friction_and_boundaries(npc: Dict[str, Any]) -> List[str]:
    """
    Extracts concrete behavioral pushback directives derived from Dislikes and Traits.
    NPC actively pushes back against these behaviors instead of being a yes-man.
    """
    if not isinstance(npc, dict):
        return []

    name = str(npc.get("name") or "Character").strip()
    basic = npc.get("basic_info") or {}
    role = str(npc.get("role") or basic.get("role") or "").lower()
    prefs = npc.get("preferences") or []
    traits = npc.get("unlocked_traits") or npc.get("traits") or basic.get("traits") or []
    trait_names = [str(t.get("name") if isinstance(t, dict) else t).lower() for t in traits if t]

    _, dislikes = categorize_likes_and_dislikes(
        prefs, traits=traits, role=role, race=npc.get("race", ""), desc=basic.get("description", "")
    )

    friction: List[str] = []
    dislike_text = " ".join(dislikes).lower()

    if any(k in dislike_text for k in ("arrogance", "boast", "condescend", "ego")):
        friction.append(f"{name} rejects arrogant posturing; responds with cool sarcasm if the player boasts or patronizes.")
    if any(k in dislike_text for k in ("dishonesty", "lies", "deceit", "fake")):
        friction.append(f"{name} despises dishonesty; immediately becomes guarded and questions motives if caught in a falsehood.")
    if any(k in dislike_text for k in ("crowd", "noise", "commotion")):
        friction.append(f"{name} dislikes crowded spectacles; visibly withdraws or pulls toward privacy if a scene gets too loud.")
    if any(k in dislike_text for k in ("laziness", "slacking", "neglect")):
        friction.append(f"{name} has zero tolerance for slacking; voices stern irritation if obligations are shirked.")

    if any(t in trait_names for t in ("proud", "dignified", "noble")):
        friction.append(f"{name} possesses immense personal pride; refuses pity and pushes back sharply against commands.")
    elif any(t in trait_names for t in ("stubborn", "rebellious", "defiant")):
        friction.append(f"{name} is instinctively contrarian; dug-in heels if pressured without reasoned persuasion.")
    elif any(t in trait_names for t in ("shy", "introverted", "guarded")):
        friction.append(f"{name} values personal boundaries; retreats into quiet silence if prodded too aggressively about personal life.")

    if not friction and dislikes:
        clean_d = re.sub(r'^(dislikes?|hates?|averse to)\s+', '', dislikes[0], flags=re.IGNORECASE).strip()
        friction.append(f"{name} has a strong aversion to {clean_d.lower()} and pushes back if subjected to it.")

    return friction[:3]


def determine_situational_layer(
    session: Dict[str, Any],
    npc: Dict[str, Any],
    actions: List[Any] = None,
    in_active_erotic: bool = False,
) -> int:
    """
    Determines situational persona tier:
      - 3: Active Intimacy / Erotic Scene (undress, sexual contact, active erotic dialogue)
      - 2: Romantic Tension / Flirtation (romantic track, affinity >= 100, romantic action, date)
      - 1: Everyday Social (Default)
    """
    scen_key = (session or {}).get("scenario", "fantasy")
    is_nsfw = is_nsfw_scenario(scen_key)

    # Check Layer 3 conditions
    if is_nsfw:
        if in_active_erotic:
            return 3

        phys_state = (session or {}).get("physical_state", {})
        if isinstance(phys_state, dict):
            intimate_contact = str(phys_state.get("intimate_contact", "")).lower()
            from mechanics.social.physical_state import is_erotic_intimate_contact
            if is_erotic_intimate_contact(intimate_contact):
                return 3

        act_text = " ".join(str(a.get("label", "") if isinstance(a, dict) else a).lower() for a in (actions or []))
        if any(kw in act_text for kw in (
            "undress", "strip", "remove clothes", "caress breasts", "stroke penis",
            "fondle", "make love", "penetrate", "oral sex", "blowjob", "cunnilingus",
            "finger", "ride", "masturbate", "climax", "orgasm"
        )):
            return 3

    # Check Layer 2 conditions
    score = npc.get("relationship_score", 0)
    track = str(npc.get("track", "platonic")).lower()

    rev_flags = dict(npc.get("revealed_flags") or {})
    appr = dict(npc.get("appearance") or {})
    int_prof = npc.get("intimate_profile")
    if not int_prof and npc.get("intimate_profile_json"):
        try:
            int_prof = json.loads(npc["intimate_profile_json"])
        except Exception:
            int_prof = {}
    elif isinstance(int_prof, str):
        try:
            int_prof = json.loads(int_prof)
        except Exception:
            int_prof = {}
    if isinstance(int_prof, dict):
        for k in (
            "intimate_revealed", "all_revealed", "all_intimate", "intercourse_revealed",
            "oral_revealed", "manual_revealed", "sensitive_spots_revealed", "turn_ons_revealed", "fetishes_revealed"
        ):
            if int_prof.get(k) and not rev_flags.get(k):
                rev_flags[k] = True
    intimate_revealed = (
        bool(rev_flags.get("intimate_revealed"))
        or bool(rev_flags.get("all_revealed"))
        or bool(rev_flags.get("all_intimate"))
        or bool(appr.get("intimate_revealed"))
        or bool(appr.get("all_revealed"))
        or bool(appr.get("all_intimate"))
    )

    if track == "romantic" or score >= 100 or intimate_revealed:
        return 2

    act_text = " ".join(str(a.get("label", "") if isinstance(a, dict) else a).lower() for a in (actions or []))
    if any(kw in act_text for kw in (
        "flirt", "kiss", "confess", "hold hand", "embrace", "cuddle", "date",
        "romantic", "lean close", "whisper", "blush", "compliment appearance",
        "experience", "turn on", "turn off", "virgin", "lovers", "suitors",
        "dating", "handling guys", "handling girls", "past partner", "intimate"
    )):
        return 2

    return 1


def build_actor_direction_card(
    session: Dict[str, Any],
    npc: Dict[str, Any],
    context: Any = None,
    active_partners: List[str] = None,
    actions: List[Any] = None,
    in_active_erotic: bool = False,
    player_char: Optional[Dict[str, Any]] = None,
    bystander_names: Optional[List[str]] = None,
) -> str:
    """
    Builds the unified, contextual Actor Direction Card for a present NPC.
    Cleanly segments into Layer 1, 2, and 3 based on current situational tension.
    """
    if not isinstance(npc, dict):
        return ""

    name = str(npc.get("name") or "Character").strip()
    basic = npc.get("basic_info") or {}
    role = str(npc.get("role") or basic.get("role") or npc.get("occupation") or "Resident").strip()
    score = int(npc.get("relationship_score") or 0)
    track = str(npc.get("track") or "platonic").strip().lower()
    race = str(npc.get("race") or basic.get("race") or "human").strip()
    gender = str(npc.get("gender") or basic.get("gender") or "").strip().lower()
    scen_key = (session or {}).get("scenario", "fantasy")
    is_nsfw = is_nsfw_scenario(scen_key)
    curr_min = (session or {}).get("current_minute", 480)
    curr_loc = (session or {}).get("current_location", "")
    hist = (session or {}).get("history", [])
    last_turn_text = hist[-1].get("narrative", "") if hist and isinstance(hist[-1], dict) else ""

    appr = dict(npc.get("appearance") or {})
    int_prof = npc.get("intimate_profile")
    if not int_prof and npc.get("intimate_profile_json"):
        try:
            int_prof = json.loads(npc["intimate_profile_json"])
        except Exception:
            int_prof = {}
    elif isinstance(int_prof, str):
        try:
            int_prof = json.loads(int_prof)
        except Exception:
            int_prof = {}
    if isinstance(int_prof, dict):
        for k in (
            "sensitive_spots", "turn_ons", "turn_offs", "fetishes", "desires_and_kinks",
            "act_likes", "act_dislikes", "intimate_demeanor", "intimate_dynamic", "erotic_openness",
            "undergarments", "bra", "underwear", "predetermined_intercourse", "had_first_time_with_player"
        ):
            if not appr.get(k) and int_prof.get(k):
                appr[k] = int_prof[k]
        disc = int_prof.get("disclosure_flags", {})
        if isinstance(disc, dict):
            for dfk, dfv in disc.items():
                if not appr.get(dfk):
                    appr[dfk] = dfv
    traits = npc.get("unlocked_traits") or npc.get("traits") or basic.get("traits") or []
    traits_clean = [str(t.get("name") if isinstance(t, dict) else t).strip() for t in traits if t]
    mannerisms_raw = npc.get("mannerisms") or basic.get("mannerisms") or ""
    voice_tone = str(npc.get("voice_tone") or basic.get("voice_tone") or "").strip()
    prefs = npc.get("preferences") or []

    # Resolve player_char and bystander_names defaults if not supplied
    if player_char is None and isinstance(session, dict):
        party = session.get("party") or []
        lead_char = party[0][0] if party and isinstance(party[0], (tuple, list)) else (party[0] if party and isinstance(party[0], dict) else {})
        if not lead_char and actions and isinstance(actions[0], dict) and isinstance(actions[0].get("char"), dict):
            lead_char = actions[0]["char"]
        player_char = lead_char

    if bystander_names is None and isinstance(session, dict):
        stage_npcs = session.get("pre_turn_stage_npcs") or session.get("current_npcs") or []
        dps_lower = {str(dp).lower().strip() for dp in (active_partners or [])}
        p_low = name.lower().strip()
        bystander_names = [
            n.get("name") for n in stage_npcs
            if isinstance(n, dict) and n.get("name")
            and n.get("name").lower().strip() != p_low
            and n.get("name").lower().strip() not in dps_lower
        ]

    # Calculate Info Level and Revealed Flags for selective disclosure
    info_lvl = get_unlocked_info_level(score)
    rev_flags = dict(npc.get("revealed_flags") or {})
    if isinstance(appr, dict):
        for k_f in (
            "intimate_revealed", "intercourse_revealed", "oral_revealed", "manual_revealed",
            "demeanor_revealed", "dynamic_revealed", "openness_revealed",
            "sensitive_spots_revealed", "turn_ons_revealed", "fetishes_revealed",
            "act_preferences_revealed", "underwear_revealed", "mannerisms_revealed", "all_revealed"
        ):
            if appr.get(k_f):
                rev_flags[k_f] = True

    intimate_unlocked = (
        (info_lvl >= 3)
        or rev_flags.get("intimate_revealed")
        or rev_flags.get("all_revealed")
        or rev_flags.get("intercourse_revealed")
        or rev_flags.get("oral_revealed")
        or rev_flags.get("manual_revealed")
    )
    sens_unlocked = intimate_unlocked or rev_flags.get("sensitive_spots_revealed") or appr.get("sensitive_spots_revealed")
    turns_unlocked = intimate_unlocked or rev_flags.get("turn_ons_revealed") or appr.get("turn_ons_revealed")
    fet_unlocked = intimate_unlocked or rev_flags.get("fetishes_revealed") or appr.get("fetishes_revealed")

    # Determine Situational Layer
    layer = determine_situational_layer(session, npc, actions=actions, in_active_erotic=in_active_erotic)

    lines: List[str] = []
    faction_k = basic.get("faction") or basic.get("faction_affiliation") or basic.get("club") or npc.get("faction")
    fac_str = f" | Faction: {faction_k}" if (faction_k and str(faction_k).lower() != "none") else ""

    lines.append(f"ACTOR DIRECTION CARD — {name} [{role} | {format_race_display(race)}{fac_str}]:")

    # ── Layer 1: Situational Presence & Agency ──
    activity = derive_scene_activity(npc, location=curr_loc, current_minute=curr_min, scen_key=scen_key)
    agenda = derive_immediate_agenda(npc, session=session, actions=actions)

    lines.append("[Situational Presence & Agency]")
    lines.append(f"  * Physical Activity: {activity}")
    lines.append(f"  * Immediate Agenda: {agenda}")

    # Micro-Blocking & Prop Continuity
    blocking = npc.get("micro_blocking")
    if not blocking and isinstance(session, dict):
        scene_stage_state = session.get("scene_stage_state", {})
        npc_k = name.strip().lower()
        npc_first = (npc_k.split() or [""])[0]
        st_match = scene_stage_state.get(npc_k) or (scene_stage_state.get(npc_first) if len(npc_first) >= 3 else None)
        if st_match and "micro_blocking" in st_match:
            blocking = st_match["micro_blocking"]
    if not blocking:
        time_block = get_time_block_key(curr_min)
        s_role = npc.get("stage_role", "active_partner" if (active_partners and any(name.lower() == p.lower() for p in active_partners)) else "room_bystander")
        blocking = derive_initial_micro_blocking(npc, current_location=curr_loc, time_slot=time_block, stage_role=s_role)

    spot = blocking.get("spot_and_posture", "resting comfortably in the room")
    prop = blocking.get("active_prop", "personal belongings")
    focus = blocking.get("prop_focus", "paused_attentive")
    prox = blocking.get("proximity", "conversational_distance")

    if not in_active_erotic:
        lines.append(f"  * Physical Blocking & Prop: Proximity is {prox.replace('_', ' ')}; currently {spot} with {prop} (Prop Focus: {focus.replace('_', ' ')}).")
        lines.append(f"  * [CHOICE & PROP GROUNDING: `next_choices` should include at least 1 option that interacts with {name}'s physical spot, proximity, or active prop ({prop}).]")

    # Live Scene Composure Momentum
    comp_state = npc.get("composure_state")
    if not comp_state and isinstance(session, dict):
        scene_stage_state = session.get("scene_stage_state", {})
        npc_k = name.strip().lower()
        npc_first = (npc_k.split() or [""])[0]
        st_match = scene_stage_state.get(npc_k) or (scene_stage_state.get(npc_first) if len(npc_first) >= 3 else None)
        if st_match and "composure_state" in st_match:
            comp_state = st_match["composure_state"]
    if comp_state and comp_state != "composed":
        if comp_state == "suspicious":
            lines.append("  * Live Scene Composure: Suspicious (narrow-eyed and guarded; probing for ulterior motives or inconsistencies).")
        else:
            lines.append(f"  * Live Scene Composure: {comp_state.replace('_', ' ').capitalize()} (actively reflect this emotional momentum in speech and reactions).")

    if voice_tone:
        lines.append(f"  * Spoken Cadence & Tone: {voice_tone}")
    elif traits_clean:
        lines.append(f"  * Spoken Cadence & Tone: Shaped authentically by traits ({', '.join(traits_clean)})")

    # Trait Behavioral Prompt & Shameless/Bold Directives
    if traits_clean:
        t_block = format_trait_behavioral_prompt(traits_clean, partner_name=name)
        if t_block:
            lines.append(f"  * Trait Directives: {t_block.strip()}")

    demeanor_val = str(npc.get("demeanor") or basic.get("demeanor") or "").lower()
    persona_val = str(npc.get("persona") or basic.get("persona") or "").lower()
    open_temp = str(appr.get("erotic_openness") or appr.get("openness") or "").lower()
    is_shameless = any(k in demeanor_val or k in persona_val or any(k in t.lower() for t in traits_clean) or k in open_temp for k in ("shameless", "lewd", "provocative", "seductive", "hedonist", "nympho", "lascivious", "pervert"))
    is_bold = any(k in demeanor_val or k in persona_val or any(k in t.lower() for t in traits_clean) or k in open_temp for k in ("bold", "flirtatious", "uninhibited", "forward"))
    is_prude = any(k in demeanor_val or k in persona_val or any(k in t.lower() for t in traits_clean) or k in open_temp for k in ("prude", "modest", "chaste", "prudish", "sheltered", "timid", "proper"))

    if is_shameless:
        lines.append(
            f"  * ⚡ SHAMELESS / LEWD SPOKEN DIALOGUE DIRECTIVE ({name}): "
            f"{name} has an unapologetically shameless and lewd disposition. In spoken dialogue, THEY HAVE NO VERBAL FILTER! "
            f"They freely make unsolicited sexual innuendos, playfully dirty remarks, cheeky double entendres, and provocative flirtations even during regular conversation and at early affinity. "
            f"DO NOT sanitize their speech or force them into bashful modesty! "
            f"However, their lack of verbal filter reflects frankness about desires and playful teasing, NOT cruelty, hostility, or fabricating fake past partners/suitors if they are a virgin!"
        )
    elif is_bold:
        lines.append(
            f"  * ⚡ BOLD / UNINHIBITED SPOKEN DIALOGUE DIRECTIVE ({name}): "
            f"{name} is bold, confident, and uninhibited. In spoken dialogue, they speak their mind openly, flirt proactively, and meet romantic or suggestive topics without stammering or awkward shame."
        )

    # Physical Stature & Height Contrast Directive
    if player_char:
        pl_app = player_char.get("appearance", {}) if isinstance(player_char.get("appearance"), dict) else {}
        pl_stature = pl_app.get("stature") or pl_app.get("height") or "average"
        pl_physique = pl_app.get("physique") or ""
        pl_gender = str(player_char.get("gender", "male")).strip().lower()
        p_stature = appr.get("stature") or appr.get("height") or "average"
        p_physique = appr.get("physique") or ""
        p_gender = str(gender or "female").strip().lower()
        stature_dir = format_stature_and_physique_narrative_directive(
            partner_name=name,
            npc_stature=p_stature,
            npc_physique=p_physique,
            npc_gender=p_gender,
            npc_race=race,
            player_stature=pl_stature,
            player_physique=pl_physique,
            player_gender=pl_gender,
            demeanor=str(appr.get("intimate_demeanor") or "").strip(),
            dynamic=str(appr.get("intimate_dynamic") or appr.get("dynamic") or "").strip()
        )
        if stature_dir:
            lines.append(stature_dir)

    # Visual Appearance
    eye = (appr.get("eye_color") or "").replace("_", " ").title()
    h_col = (appr.get("hair_color") or "").title()
    h_len = (appr.get("hair_length") or "").lower()
    h_sty = (appr.get("hair_style") or "").lower()
    stature = (appr.get("stature") or "").replace("_", " ").lower()
    physique = (appr.get("physique") or "").strip()
    coat = (appr.get("coat_color") or appr.get("fur_color") or appr.get("scale_color") or appr.get("feather_color") or "").strip()
    skin = (appr.get("skin_color") or "").strip()
    feat = (appr.get("distinctive_features") or "").strip()
    outfit = (appr.get("outfit_style") or "").strip()

    is_dyed = bool(appr.get("is_dyed"))
    if not is_dyed and coat and is_contrasting_shade(coat, h_col):
        is_dyed = True
    nat_hair = (appr.get("natural_hair_color") or "").strip()
    if not nat_hair and is_dyed and coat:
        nat_hair = infer_natural_hair_color_from_coat(coat, race=race)

    vis_parts = []
    if eye:
        vis_parts.append(f"{eye} eyes")
    if h_col or h_len or h_sty:
        h_desc = f"{h_len} {h_sty} {h_col} hair".strip()
        if is_dyed and nat_hair and nat_hair.lower() != h_col.lower():
            h_desc += f" (dyed; naturally {nat_hair.lower()})"
        elif is_dyed:
            h_desc += " (dyed)"
        vis_parts.append(h_desc)
    if stature:
        stat_s = f"{stature} stature"
        if physique:
            stat_s += f" ({physique})"
        vis_parts.append(stat_s)
    if coat and coat.lower() not in ("none", "unknown", "n/a"):
        c_lower = coat.lower()
        if any(term in c_lower for term in ("fur", "coat", "scales", "scale", "feather", "fleece", "pelt", "hide")):
            vis_parts.append(coat)
        else:
            vis_parts.append(f"{coat} coat")
    elif skin and skin.lower() not in ("none", "unknown", "n/a"):
        s_lower = skin.lower()
        if "skin" in s_lower or "complexion" in s_lower:
            vis_parts.append(skin)
        else:
            vis_parts.append(f"{skin} skin")
    if feat and feat.lower() not in ("none", "unknown"):
        vis_parts.append(feat)
    if outfit and outfit.lower() not in ("none", "unknown"):
        vis_parts.append(f"wearing {outfit}")

    if vis_parts:
        lines.append(f"  * Visual Presentation: {', '.join(vis_parts)}")

    # Canon Visual Appearance Guardrail
    key_features = []
    if coat and coat.lower() not in ("none", "unknown", "n/a"):
        key_features.append(f"coat/fur: {coat}")
    elif skin and skin.lower() not in ("none", "unknown", "n/a"):
        key_features.append(f"skin: {skin}")
    if h_col:
        if is_dyed and nat_hair and nat_hair.lower() != h_col.lower():
            key_features.append(f"hair: {h_col} (dyed; naturally {nat_hair.lower()})")
        elif is_dyed:
            key_features.append(f"hair: {h_col} (dyed)")
        else:
            key_features.append(f"hair: {h_col} (natural)")
    if eye:
        key_features.append(f"eyes: {eye}")

    if key_features:
        lines.append(
            f"  * 🎨 CANON VISUAL APPEARANCE GUARDRAIL ({name}): "
            f"Canonical physical appearance is strictly established ({'; '.join(key_features)}). "
            f"Maintain strict descriptive fidelity; NEVER contradict, alter, or confuse their coat/fur, skin, or hair colors in narration."
        )

    # ── Behavioral Cues & Mannerisms ──
    raw_manners = format_mannerisms_list(
        mannerisms_raw, race=race, desc=basic.get("description", ""), traits=traits_clean, role=role
    )
    cat_manners = format_mannerisms_categorized(
        mannerisms_raw, traits=traits_clean, role=role, race=race,
        desc=basic.get("description", ""), history_text=last_turn_text
    )
    lines.append("[Behavioral Cues & Mannerisms]")
    if raw_manners:
        lines.append(f"  * Mannerisms & Habits: {'; '.join(raw_manners)}")
    if cat_manners["idle"]:
        lines.append(f"  * [Baseline/Idle]: {'; '.join(cat_manners['idle'])}")
    if cat_manners["guarded"]:
        lines.append(f"  * [When Guarded/Stressed]: {'; '.join(cat_manners['guarded'])}")
    if cat_manners["warm"]:
        lines.append(f"  * [When Flustered/Warm]: {'; '.join(cat_manners['warm'])}")

    # ── Preferences, Likes & Dislikes ──
    likes_l, dislikes_l = categorize_likes_and_dislikes(
        prefs, traits=traits_clean, role=role, race=race, desc=basic.get("description", "")
    )
    if likes_l:
        lines.append(f"  * Likes & Desires: {', '.join(likes_l)}")
    if dislikes_l:
        lines.append(f"  * Dislikes & Aversions: {', '.join(dislikes_l)}")
    lines.append(f"  * [PREFERENCE SYNERGY: Appealing to {name}'s likes grants positive affinity (delta_score: +2 to +4); triggering {name}'s dislikes or offending them causes annoyance and negative affinity (delta_score: -1 to -4).]")

    # ── Friction & Boundaries ──
    frictions = format_friction_and_boundaries(npc)
    if frictions:
        lines.append("[Friction & Boundaries]")
        for f in frictions:
            lines.append(f"  * {f}")

    # ── Social Surface of Erotic Openness ──
    openness_val = appr.get("erotic_openness") or appr.get("openness") or ""
    if openness_val:
        lines.append(f"  * Erotic Openness: {openness_val} ({get_erotic_openness_label(openness_val)})")
        op_dir = format_openness_prompt_directive(name, openness_val)
        if op_dir:
            lines.append(op_dir)

    # ── Relational Memory & Open Threads ──
    lines.append("[Relational Standing & Open Threads]")
    lines.append(f"  * Affinity: {score}/100 ({track.capitalize()} Track)")
    emo_tone = str(npc.get("emotional_tone") or "").strip()
    if emo_tone:
        lines.append(f"  * Emotional State toward Player: {emo_tone.capitalize()}")
    open_thrd = str(npc.get("open_thread") or "").strip()
    if open_thrd:
        lines.append(f"  * Open Conversational Thread: \"{open_thrd}\" (proactively address or reference this)")

    # ── Layer 2: Romantic Tension & Private Demeanor ──
    if layer >= 2:
        lines.append("[Layer 2: Romantic Tension & Private Demeanor]")
        dem = appr.get("intimate_demeanor") or ""
        if dem:
            lines.append(f"  * Intimate Demeanor: {dem}")
            lines.append(format_demeanor_prompt_directive(name, dem))
        dyn = appr.get("intimate_dynamic") or appr.get("dynamic") or ""
        if dyn:
            lines.append(f"  * Intimate Dynamic: {dyn}")
            lines.append(format_dynamic_prompt_directive(name, dyn))

        # Desires, turn-ons & turn-offs handling with conversational disclosure and boundary gating
        turn_ons_val = clean_attribute_list_string(appr.get("turn_ons") or appr.get("desires_and_kinks") or "")
        turn_offs_val = clean_attribute_list_string(appr.get("turn_offs") or appr.get("aversions") or "")
        show_turns = bool(is_shameless or turns_unlocked or layer == 3)
        desires_to_pass = turn_ons_val if show_turns else ""

        if show_turns and turn_ons_val and str(turn_ons_val).lower() not in ("none", "unknown", ""):
            lines.append(f"  * Turn-Ons: {turn_ons_val}")
        if turn_offs_val and str(turn_offs_val).lower() not in ("none", "unknown", ""):
            lines.append(f"  * Turn-Offs: {turn_offs_val}")

        if desires_to_pass or turn_offs_val:
            t_dir = format_desires_and_turn_offs_prompt_directive(name, desires_val=desires_to_pass, turn_offs_val=turn_offs_val, dynamic_val=dyn)
            if t_dir:
                lines.append(t_dir)

        if not show_turns and (is_prude or any(k in open_temp for k in ("modest", "prude"))):
            lines.append(
                f"  * [BOUNDARY & INFORMATION GATING ({name})]: {name} is naturally guarded/modest regarding private intimacy. "
                f"When asked about their intimate experience or private desires, they hesitate, blush, or deflect the question rather than openly disclosing private details unless high trust has been established."
            )

        if sens_unlocked or layer == 3:
            sens = sanitize_sensitive_spots_for_species(
                clean_attribute_list_string(appr.get("sensitive_spots")) or "",
                race=race, distinctive_features=feat
            )
            if sens and str(sens).lower() not in ("none", "unknown"):
                lines.append(f"  * Sensitive Spots: {sens}")

        if fet_unlocked or layer == 3:
            fet = clean_attribute_list_string(appr.get("fetishes"))
            if fet and str(fet).lower() not in ("none", "unknown", "none (vanilla)"):
                lines.append(f"  * Kinks: {fet}")

        # Canon Intimacy Experience & Virginity / Dating History Grounding
        c_ic_exp = str(appr.get("intercourse_experience") or appr.get("predetermined_intercourse") or "virgin").strip().lower()
        if c_ic_exp not in ("unknown", "none", ""):
            lines.append(f"  * Intercourse Experience: {c_ic_exp.replace('_', ' ').capitalize()}")
            lines.append(f"  * Romantic Canon: Intercourse experience is '{c_ic_exp.replace('_', ' ').capitalize()}'; respect this history in confessions and dating.")
        c_or_exp = str(appr.get("oral_experience") or "inexperienced").strip().lower()
        c_man_exp = str(appr.get("manual_experience") or "inexperienced").strip().lower()
        c_an_exp = str(appr.get("anal_experience") or "inexperienced").strip().lower()
        rom_info = npc.get("relations", {}).get("romance", {}) if isinstance(npc.get("relations"), dict) else {}
        ex_partners = rom_info.get("ex_partners") or []
        curr_partner = rom_info.get("current_partner")
        has_no_dating_history = len(ex_partners) == 0 and not curr_partner
        pl_name = (player_char.get("name") if player_char else "") or "the player"

        if c_ic_exp == "virgin":
            dating_note = (
                f"{name} has ZERO prior dating, relationship, or suitor history (no ex-partners, has never dated anyone, no past suitors). "
                f"When asked about past lovers, suitors, dating experience, sexual experience, or 'handling partners/guys', {name} MUST NEVER claim to have had past sexual partners, "
                f"foreplay with past suitors, previous bedroom experience, past boyfriends, or a history of 'balancing suitors/guys on their schedule'! "
                f"They have NEVER dated, romanced, or had intimacy with anyone before meeting {pl_name}. "
                f"Even if their personality is Shameless, Bold, or Provocative, they must speak the honest truth: they have zero romantic and sexual experience. "
                f"They may tease theoretically, act confident about what they want, or banter, but they MUST NEVER fabricate fake past suitors, fake dating rosters, or previous bedroom encounters."
            ) if has_no_dating_history else (
                f"Past non-sexual relationships: {', '.join(str(ep) for ep in ex_partners)}. "
                f"When asked about past experience, {name} strictly reflects these relationships but MUST NEVER claim past sexual intercourse or bedroom encounters."
            )
            lines.append(
                f"  * CANON VIRGINITY & PAST EXPERIENCE GROUNDING ({name}): {name} is canonically a VIRGIN with NO prior intercourse experience "
                f"(Intercourse: virgin, Oral: {c_or_exp}, Manual: {c_man_exp}, Anal: {c_an_exp}). {dating_note}"
            )
        elif c_ic_exp not in ("unknown", "none", ""):
            ex_str = f"Ex-partners: {', '.join(str(ep) for ep in ex_partners)}" if ex_partners else "No past long-term relationships"
            lines.append(
                f"  * CANON PAST INTIMACY & RELATIONSHIP EXPERIENCE ({name}): Intercourse: {c_ic_exp}, Oral: {c_or_exp}, Manual: {c_man_exp}, Anal: {c_an_exp}. {ex_str}. "
                f"When asked about past experience, {name} strictly reflects these canon attributes and cannot invent unlisted partners or experiences."
            )

        # Protagonist Gender & Attraction Target Integrity
        if player_char:
            pl_gender = str(player_char.get("gender", "male")).strip().lower()
            pl_name = player_char.get("name") or "Player"
            pl_pronoun = "he/him" if "male" in pl_gender and "female" not in pl_gender else ("she/her" if "female" in pl_gender else "they/them")
            is_pl_male = "male" in pl_gender and "female" not in pl_gender
            pl_target_attraction = "a GIRL / WOMAN / FEMALE PARTNER" if is_pl_male else "a GUY / MAN / MALE PARTNER"
            lines.append(
                f"  * PROTAGONIST GENDER & ATTRACTION TARGET INTEGRITY ({name}): The player character ({pl_name}) is canonically {pl_gender.upper()} ({pl_pronoun}). "
                f"When {name} flirts with, teases, or asks {pl_name} what they look for in romance or dating, {name} MUST ask what {pl_name} is looking for in {pl_target_attraction}! "
                f"STRICTLY FORBIDDEN: NEVER invert attraction or mistakenly ask a male player flirting with a female NPC 'what are you looking for in a guy?'. Keep gender and romantic attraction coherent!"
            )

    # ── Situational Privacy & Alone Together Directive ──
    if layer >= 2 or is_nsfw:
        curr_loc_low = curr_loc.lower()
        is_private_room = any(k in curr_loc_low for k in ("bedroom", "dorm", "private room", "inn room", "quarters", "personal chamber", "bath", "onsen", "cabin", "tent"))
        is_alone_together = (not bystander_names) or is_private_room
        is_prude = any(k in demeanor_val or any(k in t.lower() for t in traits_clean) or k in open_temp for k in ("prude", "modest", "chaste", "prudish", "sheltered", "timid", "proper"))
        dyn_val = str(appr.get("intimate_dynamic") or appr.get("dynamic") or "").strip()

        if is_alone_together:
            if is_prude:
                lines.append(
                    f"  * [SITUATIONAL PRIVACY & MODESTY ({name})]: You and {name} are alone together (no other characters present). "
                    f"However, {name} is naturally modest/prude: they remain bashful and flustered around direct advances, "
                    f"treasuring gentle emotional bonding before overt physical passion."
                )
            else:
                loc_name = curr_loc or "the current secluded spot"
                d_low = dyn_val.lower()
                is_receptive = any(k in d_low for k in ("receptive", "yielding", "submissive", "surrender", "docile", "meek", "gentle"))
                is_service = any(k in d_low for k in ("service", "pamper", "devoted", "pleasing", "worship"))
                if is_receptive:
                    posture = (
                        f"They welcome mutual passion wholeheartedly, melting into your touch, inviting you to take complete charge, "
                        f"whispering breathless desires without bashful public hesitation!"
                    )
                elif is_service:
                    posture = (
                        f"They eagerly pamper, attend, and worship you with tender physical devotion without fear of onlookers!"
                    )
                else:
                    posture = (
                        f"They can be openly passionate, affectionate, and physically forward—freely initiating touch, pulling you close, "
                        f"or whispering intimate thoughts without awkward hesitation or fear of being seen."
                    )
                lines.append(
                    f"  * [ALONE TOGETHER & OPEN PASSION ({name})]: You and {name} are ALONE TOGETHER with NO bystanders present to interrupt or judge (Location: {loc_name}). "
                    f"If you two share romantic or mutual attraction, {name} is COMPLETELY UNCONSTRAINED by public modesty! "
                    f"{posture}"
                )
        else:
            other_names_str = ", ".join(bystander_names)
            lines.append(f"[PRIVATE PROFILE NOTE: The intimate profile below belongs exclusively to {name}. Other characters in the scene ({other_names_str}) have NO knowledge of these details and must NEVER reference or react to them.]")
            fet_val = str(appr.get("fetishes") or "")
            has_public_thrill = any(k in fet_val.lower() for k in ("public", "exhibition", "voyeur", "outdoor", "thrill", "danger"))
            if is_shameless or has_public_thrill:
                lines.append(
                    f"  * [PUBLIC AUDACITY & THRILL ({name})]: Other characters ({other_names_str}) are present in the room, but {name} is Shameless / thrives on the thrill! "
                    f"They openly drop cheeky double entendres, audacious innuendos, playful winks, or subtle physical touches just out of sight of onlookers."
                )
            else:
                lines.append(
                    f"  * [PUBLIC DECORUM & DISCRETION ({name})]: Other characters ({other_names_str}) are present in the room. "
                    f"Unless privately secluded, {name} maintains situational decorum in public. Direct displays of affection are subtle "
                    f"(lingering glances, secret smiles, private hand brushes) rather than blatant public scenes."
                )

    # ── Layer 3: Active Intimacy & Anatomy Directive ──
    if layer == 3:
        lines.append("[Layer 3: Active Intimacy & Anatomy Directive]")

        # Undergarments
        bra = appr.get("bra") or appr.get("bra_style") or ""
        panties = appr.get("underwear") or appr.get("panties") or appr.get("underwear_style") or ""
        ug_color = appr.get("undergarment_color") or ""
        if bra or panties:
            ug_desc = f"{ug_color} {bra} and {panties}".strip() if bra and panties else f"{ug_color} {bra or panties}".strip()
            lines.append(f"  * Undergarments: Wearing {ug_desc}")
        elif appr.get("is_braless") or appr.get("braless"):
            lines.append("  * Undergarments: Braless / Commando")

        # Canon Undergarments Grounding (Commando / Bra-less prohibitions)
        p_under = appr.get("undergarments") if isinstance(appr.get("undergarments"), dict) else {}
        und_raw = str(p_under.get("underwear") or appr.get("underwear") or appr.get("panties") or "").strip()
        bra_raw = str(p_under.get("bra") or appr.get("bra") or "").strip()
        is_p_commando = any(k in und_raw.lower() for k in ("none", "commando", "freeball"))
        is_p_braless = any(k in bra_raw.lower() for k in ("none", "bra-less", "braless", "free")) or bool(appr.get("is_braless") or appr.get("braless"))
        if is_p_commando or is_p_braless:
            u_dirs = []
            if is_p_commando:
                u_dirs.append(
                    f"{name} is wearing NO UNDERWEAR / PANTIES (Commando). "
                    f"When their skirt, dress, or bottoms are lifted, opened, pulled down, or revealed, they are completely bare underneath! "
                    f"STRICTLY FORBIDDEN: NEVER narrate peeling back, sliding aside, or snapping panties or underwear fabric—there are no panties!"
                )
            if is_p_braless:
                u_dirs.append(
                    f"{name} is wearing NO BRA (Bra-less). Their breasts are bare and unrestrained beneath their top. "
                    f"STRICTLY FORBIDDEN: NEVER narrate unhooking or unclasping a bra!"
                )
            lines.append(f"  * CANON UNDERGARMENTS GROUNDING ({name}): {' '.join(u_dirs)}")

        # Anatomy pride / insecurity directives
        p_gender = str(gender or "female").strip().lower()
        is_male_npc = "male" in p_gender and "female" not in p_gender
        p_asset_size = str(appr.get("penis_size" if is_male_npc else "breast_size") or "").strip()
        if p_asset_size and p_asset_size.lower() not in ("none", "unknown"):
            pl_app = player_char.get("appearance", {}) if player_char and isinstance(player_char.get("appearance"), dict) else {}
            pl_gender = str(player_char.get("gender", "male")).strip().lower() if player_char else "male"
            is_pl_male = "male" in pl_gender and "female" not in pl_gender
            pl_asset_size = str(pl_app.get("penis_size" if is_pl_male else "breast_size") or "").strip()
            p_asset_tex = str(appr.get("asset_texture") or "").strip()
            body_asset = format_body_asset_narrative_directive(
                partner_name=name,
                gender=p_gender,
                asset_size=p_asset_size,
                demeanor=str(appr.get("intimate_demeanor") or "").strip(),
                openness=openness_val,
                race=race,
                undergarments=p_under,
                player_asset=pl_asset_size,
                player_gender=pl_gender,
                asset_texture=p_asset_tex,
                affinity=score,
                npc_appearance=appr,
                npc_name=name,
                npc_gender=gender
            )
            if body_asset:
                lines.append(body_asset)

        # Kinks & act preferences
        fet = clean_attribute_list_string(appr.get("fetishes"))
        if fet and str(fet).lower() not in ("none", "unknown", "none (vanilla)"):
            lines.append(format_fetish_prompt_directive(name, fet))

        act_prefs = appr.get("act_preferences") or {}
        if act_prefs:
            lines.append(format_act_preferences_prompt_directive(name, act_prefs))

        # Intimate experience canon
        exp_parts = []
        for exp_k, exp_label in (
            ("intercourse_experience", "Intercourse Experience"),
            ("oral_experience", "Oral Experience"),
            ("manual_experience", "Manual Experience"),
            ("anal_experience", "Anal Experience"),
        ):
            val = appr.get(exp_k)
            if val and str(val).lower() not in ("unknown", "none"):
                exp_parts.append(f"{exp_label}: {val.replace('_', ' ').title()}")
        if exp_parts:
            lines.append(f"  * {'; '.join(exp_parts)}")

        # Pacing & Climax Primacy
        lines.append(
            f"  * INTIMATE PACING & CLIMAX PRIMACY: Respond passionately to the player's physical touch. "
            f"Prioritize mutual arousal and the player's pleasure. "
            f"Describe visceral sensory details, breathlessness, flushed skin, and escalating excitement leading to orgasm."
        )

    return "\n".join(lines)
