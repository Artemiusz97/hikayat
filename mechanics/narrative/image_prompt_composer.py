"""
image_prompt_composer.py
Deterministic tag-based prompt composer for SDXL / Illustrious models.
Converts structured game state (scenario, entities, appearances, poses, clothing, check results)
into high-fidelity Danbooru-style prompts and determines optimal dimensions (Portrait vs Wide).
"""
from __future__ import annotations

import re
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import db

logger = logging.getLogger("hikayat.image_composer")

# Standard SDXL / Illustrious Training Bucket Dimensions
DIMENSION_PORTRAIT = "832x1216"
DIMENSION_WIDE = "1216x832"

# Curated universal negative prompt for Danbooru / SDXL / Illustrious
DEFAULT_NEGATIVE_PROMPT = (
    "lowres, bad anatomy, bad hands, missing fingers, extra digits, fewer digits, cropped, "
    "text, error, watermark, signature, username, blurry, artist name, pov hand, disembodied hand, "
    "extra limbs, mutated anatomy, worst quality, low quality, jpeg artifacts, normal quality"
)

# Base quality tokens always prepended
BASE_QUALITY_TOKENS = "masterpiece, best quality, very aesthetic, absurdres"

# Scenario-specific base style tokens (strictly aesthetic/style, NOT entity species)
SCENARIO_STYLE_TOKENS = {
    "high_school_drama": "anime, visual novel cg, cel shaded, clean lineart, vibrant anime colors, key visual",
    "furry_high_school_drama": "anime, visual novel cg, cel shaded, clean lineart, vibrant anime colors, key visual",
    "nsfw_high_school_drama": "anime, visual novel cg, cel shaded, clean lineart, vibrant anime colors, key visual",
    "nsfw_furry_high_school_drama": "anime, visual novel cg, cel shaded, clean lineart, vibrant anime colors, key visual",
    "fantasy": "fantasy anime, visual novel cg, digital media, clean lineart, atmospheric lighting, key visual",
    "isekai_fantasy": "fantasy anime, visual novel cg, digital media, clean lineart, atmospheric lighting, key visual",
    "nsfw_isekai_fantasy": "fantasy anime, visual novel cg, digital media, clean lineart, atmospheric lighting, key visual",
    "dark_fantasy": "dark fantasy anime, visual novel cg, moody cinematic lighting, intricate shadows, clean lineart",
    "cyberpunk": "cyberpunk anime, sci-fi anime, neon lighting, clean lineart, futuristic city visual novel cg",
    "sci_fi": "sci-fi anime, space opera aesthetic, clean lineart, visual novel cg, futuristic lighting",
    "steampunk": "steampunk anime, victorian aesthetic, brass and steam, visual novel cg, clean lineart",
}
DEFAULT_STYLE_TOKENS = "anime, visual novel cg, cel shaded, clean lineart, vibrant colors"


@dataclass
class ComposedImagePrompt:
    prompt: str
    negative_prompt: str
    size: str
    orientation: str  # "portrait" | "wide"
    focal_npc: Optional[str] = None
    character_count: int = 0


def _clean_tag(tag: str) -> str:
    """Cleans up redundant spaces and trailing punctuation for Danbooru tags."""
    if not tag:
        return ""
    t = tag.strip().strip(",").strip(".").strip()
    return t.lower()


def _join_tags(*parts: Any) -> str:
    """Joins non-empty tag strings with comma separators."""
    clean_parts = []
    for p in parts:
        if not p:
            continue
        if isinstance(p, (list, tuple)):
            for item in p:
                ct = _clean_tag(str(item))
                if ct and ct not in clean_parts:
                    clean_parts.append(ct)
        else:
            ct = _clean_tag(str(p))
            if ct and ct not in clean_parts:
                clean_parts.append(ct)
    return ", ".join(clean_parts)


def format_species_tags(race: str = "", species: str = "", bio: str = "") -> str:
    """
    Formats the character species according to user specification:
    - Full Beastfolk: 'anthro, kemono, <species>'
    - Half Beast / Hybrid: 'human, <species> ears, <species> tail'
    - Human: 'human'
    - Elf: 'elf, pointy ears'
    - Dwarf: 'dwarf'
    """
    r_low = (race or "").strip().lower()
    s_low = (species or "").strip().lower()
    b_low = (bio or "").strip().lower()
    combined = f"{r_low} {s_low} {b_low}"

    # Extract animal species name if prefixed with beastfolk: or half_beast:
    spec_target = ""
    if ":" in r_low:
        prefix, sub = r_low.split(":", 1)
        spec_target = sub.strip()
    elif s_low:
        spec_target = s_low
    else:
        # Check known animal tokens in combined
        for animal in ("cat", "fox", "wolf", "rabbit", "bunny", "tiger", "lion", "cheetah",
                       "fennec", "mouse", "rat", "bear", "bird", "hawk", "raven", "snake",
                       "reptile", "dragon", "dog", "canine", "feline", "panther"):
            if re.search(rf"\b{animal}\b", combined):
                spec_target = "cat" if animal in ("feline",) else ("wolf" if animal in ("dog", "canine") else animal)
                break

    is_half = (
        r_low.startswith("half_beast")
        or r_low.startswith("half-beast")
        or r_low.startswith("hybrid")
        or "kemonomimi" in combined
        or "half-beast" in combined
        or "half beast" in combined
        or "nekomimi" in combined
    )

    is_beastfolk = (
        r_low.startswith("beastfolk")
        or "beastfolk" in combined
        or "anthro" in combined
        or "furry" in combined
        or (spec_target and not is_half and ("fur" in combined or "coat" in combined or "paws" in combined))
    )

    if is_half and spec_target:
        return f"human, {spec_target} ears, {spec_target} tail"
    if is_beastfolk and spec_target:
        return f"anthro, kemono, {spec_target}"
    if is_half:
        return "human, animal ears, animal tail"
    if is_beastfolk:
        return "anthro, kemono"

    # Fantasy & human races
    if "elf" in r_low or "elven" in r_low:
        return "elf, pointy ears"
    if "dwarf" in r_low or "dwarven" in r_low:
        return "dwarf"
    if "goblin" in r_low:
        return "goblin, green skin, pointy ears"
    if "demon" in r_low or "tiefling" in r_low:
        return "demon horns, demon tail"

    return "human"


def format_npc_appearance_tags(npc_data: Dict[str, Any], intimate_context: bool = False) -> str:
    """Extracts physical Danbooru tags for an NPC from their appearance dictionary."""
    app = npc_data.get("appearance") or {}
    if not isinstance(app, dict):
        app = {}

    tags = []

    # 1. Species / Race
    race = npc_data.get("race") or app.get("race") or ""
    species = npc_data.get("species") or app.get("species") or ""
    bio = npc_data.get("description") or ""
    spec_tags = format_species_tags(race=race, species=species, bio=bio)
    if spec_tags:
        tags.append(spec_tags)

    # 2. Eyes
    eye_col = app.get("eye_color") or ""
    if eye_col:
        clean_eye = eye_col.lower()
        for kw, repl in (("emerald green", "green"), ("sapphire blue", "blue"), ("ruby red", "red"),
                         ("emerald", "green"), ("sapphire", "blue"), ("ruby", "red"), ("amethyst", "purple")):
            clean_eye = clean_eye.replace(kw, repl)
        clean_eye = " ".join(dict.fromkeys(clean_eye.split()))  # deduplicate repeated words
        tags.append(f"{clean_eye} eyes")

    # 3. Hair
    hair_col = app.get("hair_color") or ""
    hair_style = app.get("hair_style") or ""
    hair_len = app.get("hair_length") or ""
    hair_parts = [p for p in (hair_len, hair_style, hair_col) if p]
    if hair_parts:
        tags.append(f"{' '.join(hair_parts)} hair")

    # 4. Fur / Skin / Coat / Scales
    coat_col = app.get("coat_color") or ""
    skin_col = app.get("skin_color") or ""
    if coat_col:
        c_low = coat_col.lower()
        if "scale" in c_low:
            clean_coat = c_low.replace("scales", "").replace("scale", "").strip()
            tags.append(f"{clean_coat} scales")
        elif "feather" in c_low:
            clean_coat = c_low.replace("feathers", "").replace("feather", "").strip()
            tags.append(f"{clean_coat} feathers")
        elif "fur" not in spec_tags:
            clean_coat = c_low.replace("fur", "").replace("coat", "").strip()
            tags.append(f"{clean_coat} fur")
    elif skin_col:
        tags.append(f"{skin_col.lower()} skin")

    # 5. Distinctive features (ears, tails, scars)
    dist = app.get("distinctive_features") or ""
    if dist:
        # e.g. "fluffy calico tail, cat ears"
        for f in dist.split(","):
            cf = f.strip().lower()
            if cf and cf not in tags and cf not in spec_tags:
                tags.append(cf)

    # 6. Outfit & Clothing State
    outfit = app.get("outfit_style") or ""
    clothing_state = npc_data.get("_clothing_state") or {}
    top_state = clothing_state.get("top", "clothed")
    bot_state = clothing_state.get("bottom", "clothed")

    if top_state == "off" and bot_state == "off":
        tags.append("nude")
    elif top_state == "disheveled" or bot_state == "disheveled":
        tags.append("disheveled clothes, messy outfit")
        if outfit:
            tags.append(outfit)
    elif top_state == "off":
        tags.append("topless, bare chest")
        if outfit:
            tags.append(outfit)
    elif bot_state == "off":
        tags.append("bottomless")
        if outfit:
            tags.append(outfit)
    elif outfit:
        tags.append(outfit)
    else:
        tags.append("school uniform, collared shirt, pleated skirt" if "school" in str(npc_data.get("role", "")).lower() else "casual clothes")

    # 7. Assets (if intimate/NSFW context)
    if intimate_context and str(npc_data.get("gender", "")).lower() in ("female", "f", "woman", "girl"):
        breast = str(app.get("breast_size") or "").lower()
        if any(kw in breast for kw in ("dd", "e-cup", "f-cup", "huge", "voluptuous")):
            tags.append("large breasts")
        elif any(kw in breast for kw in ("c-cup", "d-cup", "bouncy")):
            tags.append("medium breasts")
        elif any(kw in breast for kw in ("a-cup", "petite", "flat", "small")):
            tags.append("small breasts")

    return _join_tags(tags)


def format_expression_tags(check_tier: str = "", action_label: str = "", intimate_context: bool = False) -> str:
    """Maps skill check tier and action context to Danbooru expression tags."""
    if intimate_context:
        return "blushing, flushed face, parted lips, heavy breathing, half-closed eyes, aroused"

    tier_clean = (check_tier or "").lower()
    if "crit_success" in tier_clean or "crit_pass" in tier_clean:
        return "blushing, joyful smile, sparkling eyes, happy"
    if "success" in tier_clean or "pass" in tier_clean:
        return "calm, slight smile, confident expression, gentle gaze"
    if "crit_fail" in tier_clean:
        return "shocked, flustered, blushing deeply, wide eyes, embarrassed"
    if "fail" in tier_clean:
        return "annoyed, looking away, furrowed brow, pouting"

    return "slight smile, neutral expression, looking at viewer"


def format_pose_tags(pose_dict: Dict[str, Any]) -> str:
    """Extracts posture and holding tags from actor_poses."""
    if not isinstance(pose_dict, dict):
        return "standing, facing viewer"
    tags = []
    posture = str(pose_dict.get("posture") or "").lower().strip()
    holding = str(pose_dict.get("holding") or "").lower().strip()

    if posture:
        if "seat" in posture or "sit" in posture:
            tags.append("seated at desk")
        elif "kneel" in posture:
            tags.append("kneeling")
        elif "lean" in posture:
            tags.append("leaning back")
        elif "prone" in posture or "lying" in posture:
            tags.append("lying on back")
        else:
            tags.append(posture)

    if holding and holding not in ("none", "empty hands", "empty"):
        tags.append(f"holding {holding}")

    return _join_tags(tags) or "standing, facing viewer"


def format_scenery_tags(location: str = "", scene_title: str = "") -> str:
    """Parses location string into clean Danbooru background tags."""
    loc_clean = (location or scene_title or "").lower()
    tags = []

    # Classroom / School
    if any(kw in loc_clean for kw in ("class", "homeroom", "academy", "school")):
        tags.extend(["classroom", "wooden desks", "green chalkboard", "large windows", "indoor", "afternoon sunlight"])
    elif any(kw in loc_clean for kw in ("library", "stacks", "archives")):
        tags.extend(["library", "bookshelves", "rows of books", "wooden tables", "indoor", "warm lighting"])
    elif any(kw in loc_clean for kw in ("hallway", "corridor")):
        tags.extend(["school hallway", "lockers", "large windows", "indoor"])
    elif any(kw in loc_clean for kw in ("rooftop", "roof")):
        tags.extend(["school rooftop", "chain-link fence", "open sky", "afternoon breeze", "cloudy sky"])
    elif any(kw in loc_clean for kw in ("bedroom", "dorm", "room")):
        tags.extend(["bedroom", "bed", "warm lamp lighting", "indoor", "curtains"])
    elif any(kw in loc_clean for kw in ("dungeon", "crypt", "cave")):
        tags.extend(["dark dungeon", "stone walls", "torches", "dimly lit", "mossy stones"])
    elif any(kw in loc_clean for kw in ("forest", "woods", "grove")):
        tags.extend(["forest", "ancient trees", "sunbeams through trees", "pathway", "nature"])
    elif any(kw in loc_clean for kw in ("tavern", "inn", "bar")):
        tags.extend(["fantasy tavern", "wooden counter", "mugs", "warm hearth", "lantern lighting", "indoor"])
    else:
        tags.extend(["detailed interior background", "ambient lighting"])

    return _join_tags(tags)


def _get_npc_profile(session_id: int, npc_name: str, session: Dict[str, Any]) -> Dict[str, Any]:
    """Retrieves or builds the NPC profile dict from DB contacts or session current_npcs."""
    clean_name = str(npc_name or "").strip()
    profile = {"name": clean_name}

    # 1. Check session current_npcs
    curr_npcs = session.get("current_npcs") or []
    for entry in curr_npcs:
        if isinstance(entry, dict) and entry.get("name") and entry["name"].strip().lower() == clean_name.lower():
            profile.update(entry)
            break

    # 2. Check DB contacts
    if session_id:
        try:
            contact = db.get_contact(session_id, clean_name)
            if contact:
                if not profile.get("race") and contact.get("race"):
                    profile["race"] = contact["race"]
                if not profile.get("gender") and contact.get("gender"):
                    profile["gender"] = contact["gender"]
                if not profile.get("species") and contact.get("species"):
                    profile["species"] = contact["species"]
                if contact.get("appearance"):
                    p_app = dict(profile.get("appearance") or {})
                    p_app.update(contact["appearance"])
                    profile["appearance"] = p_app
                if not profile.get("description") and contact.get("basic_info"):
                    profile["description"] = contact["basic_info"].get("description", "")
        except Exception as e:
            logger.debug("Failed to fetch contact for %s: %s", clean_name, e)

    return profile


def compose_turn_image_prompt(
    session: Dict[str, Any],
    outcome: Optional[Dict[str, Any]] = None,
    action: Optional[Dict[str, Any]] = None,
) -> ComposedImagePrompt:
    """
    Main entry point for assembling the SDXL / Illustrious prompt and resolution for a turn.
    """
    outcome = outcome or {}
    action = action or {}
    session_id = session.get("id") or 0
    scen_key = session.get("scenario", "fantasy")
    style_tags = SCENARIO_STYLE_TOKENS.get(scen_key, DEFAULT_STYLE_TOKENS)

    location = outcome.get("location") or session.get("current_location") or ""
    scene_title = outcome.get("scene_title") or session.get("scene_title") or ""
    scenery_tags = format_scenery_tags(location=location, scene_title=scene_title)
    opening_cues = str(outcome.get("visual_cues") or session.get("opening_visual_cues") or "").strip()
    if opening_cues:
        scenery_tags = _join_tags(scenery_tags, opening_cues)

    # Check tier & action context
    check = action.get("check")
    check_tier = getattr(check, "tier", None) or (check.get("tier") if isinstance(check, dict) else None) or action.get("tier", "")
    act_intent = str(action.get("intent") or "").lower()
    act_sub_intent = str(action.get("sub_intent") or "").lower()
    is_intimate = (
        act_intent == "intimate_act"
        or any(k in act_sub_intent for k in ("kiss", "foreplay", "oral", "intercourse", "aftercare"))
        or bool(outcome.get("intimate_update"))
    )

    # Combat Check
    nearby_enemies = outcome.get("nearby_enemies") or session.get("nearby_enemies") or []
    if nearby_enemies:
        enemy = nearby_enemies[0]
        e_name = enemy.get("name", "Enemy") if isinstance(enemy, dict) else str(enemy)
        e_species = _clean_tag(e_name.replace("Warrior", "").replace("Scout", "").replace("Leader", ""))
        combat_prompt = _join_tags(
            BASE_QUALITY_TOKENS,
            style_tags,
            "1monster, combat scene, battle stance",
            f"{e_species}, glowing eyes, aggressive expression, snarling",
            "wielding weapon, dynamic combat lighting, medium shot",
            scenery_tags
        )
        return ComposedImagePrompt(
            prompt=combat_prompt,
            negative_prompt=DEFAULT_NEGATIVE_PROMPT,
            size=DIMENSION_WIDE,
            orientation="wide",
            character_count=1
        )

    # Determine NPCs in the scene (excluding player)
    dialogue_partner = outcome.get("dialogue_partner") or session.get("dialogue_partner")
    npcs_present = outcome.get("npcs_present") or session.get("current_npcs") or []
    raw_npc_names = []

    if dialogue_partner:
        raw_npc_names.append(dialogue_partner)
    for n in npcs_present:
        n_name = n.get("name") if isinstance(n, dict) else str(n)
        if n_name and n_name not in raw_npc_names:
            raw_npc_names.append(n_name)

    # Filter out player name / invalid entries
    actor_char = action.get("char") or action.get("character") or {}
    player_name = (actor_char.get("name") if isinstance(actor_char, dict) else "") or "adventurer"
    valid_npcs = [
        name for name in raw_npc_names
        if name and name.lower() not in (player_name.lower(), "you", "party", "none", "null")
    ]

    actor_poses = outcome.get("actor_poses") or {}
    physical_state = outcome.get("_physical_state") or {}
    actor_clothes = physical_state.get("actors", {}) if isinstance(physical_state, dict) else {}

    # Case 0: No NPCs present -> Pure Scenery (Wide)
    if not valid_npcs:
        scene_prompt = _join_tags(
            BASE_QUALITY_TOKENS,
            style_tags,
            "scenery, no humans, landscape",
            scenery_tags,
            "atmospheric lighting, highly detailed environment"
        )
        return ComposedImagePrompt(
            prompt=scene_prompt,
            negative_prompt=DEFAULT_NEGATIVE_PROMPT,
            size=DIMENSION_WIDE,
            orientation="wide",
            character_count=0
        )

    # Case 1: Exactly 1 NPC (or 1 focal NPC with no active partner) -> Portrait (832x1216)
    if len(valid_npcs) == 1:
        focal_name = valid_npcs[0]
        profile = _get_npc_profile(session_id, focal_name, session)
        profile["_clothing_state"] = actor_clothes.get(focal_name, {}).get("clothing", {})

        gender_raw = str(profile.get("gender") or "female").lower()
        gender_tag = "1girl" if gender_raw in ("female", "f", "woman", "girl") else "1boy"
        app_tags = format_npc_appearance_tags(profile, intimate_context=is_intimate)
        expr_tags = format_expression_tags(check_tier, action.get("label", ""), intimate_context=is_intimate)
        pose_tags = format_pose_tags(actor_poses.get(focal_name, {}))
        camera_tags = "medium shot, upper body, facing viewer, eye level, looking at viewer"

        solo_prompt = _join_tags(
            BASE_QUALITY_TOKENS,
            style_tags,
            gender_tag,
            app_tags,
            expr_tags,
            pose_tags,
            camera_tags,
            scenery_tags
        )
        return ComposedImagePrompt(
            prompt=solo_prompt,
            negative_prompt=DEFAULT_NEGATIVE_PROMPT,
            size=DIMENSION_PORTRAIT,
            orientation="portrait",
            focal_npc=focal_name,
            character_count=1
        )

    # Case 2: Multi-character (2+ NPCs) -> Wide (1216x832) using Strategy B (BREAK) + Strategy C (Cap at 2)
    npc1_name, npc2_name = valid_npcs[0], valid_npcs[1]
    p1 = _get_npc_profile(session_id, npc1_name, session)
    p2 = _get_npc_profile(session_id, npc2_name, session)
    p1["_clothing_state"] = actor_clothes.get(npc1_name, {}).get("clothing", {})
    p2["_clothing_state"] = actor_clothes.get(npc2_name, {}).get("clothing", {})

    g1 = "girl" if str(p1.get("gender", "female")).lower() in ("female", "f", "woman", "girl") else "boy"
    g2 = "girl" if str(p2.get("gender", "female")).lower() in ("female", "f", "woman", "girl") else "boy"

    if g1 == "girl" and g2 == "girl":
        count_tag = "2girls"
    elif g1 == "boy" and g2 == "boy":
        count_tag = "2boys"
    else:
        count_tag = "1boy, 1girl"

    app1 = format_npc_appearance_tags(p1, intimate_context=is_intimate)
    app2 = format_npc_appearance_tags(p2, intimate_context=is_intimate)
    expr1 = format_expression_tags(check_tier, action.get("label", ""), intimate_context=is_intimate)
    expr2 = "gentle smile, calm, looking at viewer"
    pose1 = format_pose_tags(actor_poses.get(npc1_name, {}))
    pose2 = format_pose_tags(actor_poses.get(npc2_name, {}))

    extra_ambient = "students in background, ambient crowd" if len(valid_npcs) > 2 else ""
    header_tags = _join_tags(
        BASE_QUALITY_TOKENS,
        style_tags,
        count_tag,
        "talking to each other, medium shot, cowboy shot",
        scenery_tags,
        extra_ambient
    )
    multi_prompt = (
        f"{header_tags}, BREAK, "
        f"{g1} on the left, {app1}, {expr1}, {pose1}, BREAK, "
        f"{g2} on the right, {app2}, {expr2}, {pose2}"
    )

    return ComposedImagePrompt(
        prompt=multi_prompt,
        negative_prompt=DEFAULT_NEGATIVE_PROMPT,
        size=DIMENSION_WIDE,
        orientation="wide",
        focal_npc=npc1_name,
        character_count=len(valid_npcs)
    )
