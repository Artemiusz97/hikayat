"""
image_prompt_composer.py
Deterministic tag-based prompt composer for SDXL / Illustrious models.
Converts structured game state (scenario, entities, appearances, poses, clothing, check results,
location hierarchy, active room props, 24-hour clock lighting, weather, and atmospheric mood)
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
    """Joins non-empty tag strings with comma separators without duplicates."""
    clean_parts: List[str] = []
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
    - Goblin: 'goblin, green skin, pointy ears'
    - Demon: 'demon horns, demon tail'
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

    tags: List[str] = []

    # 1. Species / Race
    spec_tags = format_species_tags(
        race=str(npc_data.get("race") or ""),
        species=str(npc_data.get("species") or ""),
        bio=str(npc_data.get("description") or "")
    )
    if spec_tags:
        tags.append(spec_tags)

    # 2. Eye Color
    eye_col = app.get("eye_color") or ""
    if eye_col:
        clean_eye = eye_col.lower().replace("eyes", "").strip()
        for kw, repl in (("emerald green", "green"), ("sapphire blue", "blue"), ("ruby red", "red"),
                         ("emerald", "green"), ("sapphire", "blue"), ("ruby", "red"), ("amethyst", "purple")):
            clean_eye = clean_eye.replace(kw, repl)
        clean_eye = " ".join(dict.fromkeys(clean_eye.split()))  # deduplicate repeated words
        tags.append(f"{clean_eye} eyes")

    # 3. Hair (length, style, color)
    hair_col = app.get("hair_color") or ""
    hair_len = app.get("hair_length") or ""
    hair_sty = app.get("hair_style") or ""
    hair_parts = [p.lower().strip() for p in (hair_len, hair_sty, hair_col) if p and str(p).strip()]
    if hair_parts:
        h_str = " ".join(hair_parts)
        if "hair" not in h_str:
            h_str += " hair"
        tags.append(h_str)

    # 4. Coat / Fur / Skin Color
    coat_col = app.get("coat_color") or ""
    skin_col = app.get("skin_color") or ""
    if coat_col:
        c_low = coat_col.lower()
        if "anthro" in spec_tags or "kemono" in spec_tags:
            clean_coat = c_low.replace("fur", "").replace("coat", "").strip()
            tags.append(f"{clean_coat} fur")
        elif "fur" not in spec_tags:
            clean_coat = c_low.replace("fur", "").replace("coat", "").strip()
            tags.append(f"{clean_coat} fur")
    elif skin_col:
        tags.append(f"{skin_col.lower()} skin")

    # 5. Distinctive features (ears, tails, scars)
    dist = app.get("distinctive_features") or ""
    if dist:
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


def format_pose_tags(pose_dict: Dict[str, Any], location: str = "", focal_point: str = "") -> str:
    """Extracts posture and holding tags from actor_poses, enriched by room interaction."""
    tags: List[str] = []
    posture = ""
    holding = ""
    if isinstance(pose_dict, dict):
        posture = str(pose_dict.get("posture") or "").lower().strip()
        holding = str(pose_dict.get("holding") or "").lower().strip()

    loc_focal = f"{location} {focal_point}".lower()

    if posture:
        if "seat" in posture or "sit" in posture:
            tags.append("seated at desk" if ("class" in loc_focal or "desk" in loc_focal) else "sitting down")
        elif "kneel" in posture:
            tags.append("kneeling")
        elif "lean" in posture:
            tags.append("leaning back")
        elif "prone" in posture or "lying" in posture:
            tags.append("lying on back")
        else:
            tags.append(posture)
    else:
        # Dynamic contextual pose based on room focal anchors
        if any(k in loc_focal for k in ("desk", "homeroom", "class")):
            tags.append("seated at desk, upper body, hands on table")
        elif any(k in loc_focal for k in ("infirmary", "clinic", "bed", "dorm", "bedroom")):
            tags.append("sitting on edge of bed, relaxed posture, hands resting on mattress")
        elif "window" in loc_focal:
            tags.append("leaning against windowsill, looking at viewer")
        elif any(k in loc_focal for k in ("rooftop", "roof", "railing", "balcony")):
            tags.append("leaning against railing, looking at viewer")
        elif any(k in loc_focal for k in ("hallway", "corridor", "locker")):
            tags.append("leaning against wall, standing, casual posture")
        else:
            tags.append("standing, facing viewer")

    if holding and holding not in ("none", "empty hands", "empty"):
        tags.append(f"holding {holding}")

    return _join_tags(tags) or "standing, facing viewer"


def format_time_lighting_tags(
    minute: Optional[int] = None,
    is_indoor: bool = True,
    time_desc: str = ""
) -> Tuple[str, str]:
    """
    Derives time-of-day and dynamic lighting tags from the 24-hour simulation clock.
    Returns (lighting_tags_string, time_phase_name).
    """
    try:
        from mechanics.system.time_engine import get_time_of_day_phase
    except Exception:
        get_time_of_day_phase = None

    safe_min = 600  # Default to 10:00 AM Morning
    if minute is not None:
        try:
            safe_min = int(minute) % 1440
        except Exception:
            safe_min = 600
    elif time_desc:
        td_low = str(time_desc).lower()
        if any(k in td_low for k in ("dawn", "early morning")):
            safe_min = 360
        elif "morning" in td_low:
            safe_min = 600
        elif "afternoon" in td_low:
            safe_min = 840
        elif any(k in td_low for k in ("evening", "sunset", "dusk", "twilight", "golden hour")):
            safe_min = 1080
        elif "midnight" in td_low:
            safe_min = 60
        elif "night" in td_low:
            safe_min = 1260

    phase_name = "Morning"
    if get_time_of_day_phase:
        try:
            phase_name, _, _ = get_time_of_day_phase(safe_min)
        except Exception:
            phase_name = "Morning"
    else:
        if 300 <= safe_min < 480:
            phase_name = "Early Morning"
        elif 480 <= safe_min < 720:
            phase_name = "Morning"
        elif 720 <= safe_min < 1020:
            phase_name = "Afternoon"
        elif 1020 <= safe_min < 1200:
            phase_name = "Evening"
        elif 1200 <= safe_min < 1440:
            phase_name = "Night"
        else:
            phase_name = "Midnight"

    # Indoor vs Outdoor Lighting Specifications
    if is_indoor:
        if phase_name == "Early Morning":
            tags = "indoor, soft dawn light through window, pale morning sky outside window, gentle morning shadows, early morning sunlight"
        elif phase_name == "Morning":
            tags = "indoor, large windows, bright morning sunlight through window, sunbeams, dust motes in sunlight, bright airy room"
        elif phase_name == "Afternoon":
            tags = "indoor, warm afternoon sunlight, bright room, sunlight patterns on floor, ambient daylight"
        elif phase_name == "Evening":
            tags = "indoor, sunset glow through blinds, golden hour light through window, warm orange rim lighting, long shadows, evening atmosphere"
        elif phase_name == "Night":
            tags = "indoor, dark outside window, warm interior room lights, incandescent lighting, glowing desk lamp, cozy night atmosphere"
        else:  # Midnight
            tags = "indoor, pitch black outside window, dim room lighting, solitary glowing lamp, deep dramatic shadows, late night stillness"
    else:
        if phase_name == "Early Morning":
            tags = "early morning, dawn, sunrise, soft morning light, pale pink sky, gentle morning sun, long shadows"
        elif phase_name == "Morning":
            tags = "morning, bright daylight, clear sky, sunbeams, vibrant natural light, crisp morning air"
        elif phase_name == "Afternoon":
            tags = "afternoon, bright warm sunlight, clear blue sky, high sun, sun dappled, sunny day"
        elif phase_name == "Evening":
            tags = "evening, sunset, golden hour, twilight, orange sky, dusky sky, warm rim lighting, long shadows, evening glow"
        elif phase_name == "Night":
            tags = "night, dark sky, starry sky, crescent moon, moonlight, outdoor streetlights, glowing lights, night view"
        else:  # Midnight
            tags = "midnight, deep night, pitch black sky, full moon, dim moonlight, deep mysterious shadows, quiet night"

    return tags, phase_name


def format_scenery_archetype_tags(
    location: str = "",
    scene_title: str = "",
    scenario: str = "",
) -> Tuple[str, bool]:
    """
    Parses the full 3-tier spatial location string and scenario into rich,
    architecturally specific Danbooru scenery tags and determines indoor vs outdoor context.
    Returns (scenery_tags_string, is_indoor_boolean).
    """
    text = f"{location} {scene_title}".lower()

    # Determine Outdoor vs Indoor
    outdoor_signals = (
        "rooftop", "roof", "courtyard", "quad", "campus grounds", "street", "sidewalk",
        "park", "plaza", "garden", "forest", "woods", "grove", "mountain", "lake",
        "beach", "field", "exterior", "outside", "open air", "balcony", "alley",
        "terrace", "overlook", "crossroads", "trail", "bazaar", "market square"
    )
    indoor_signals = (
        "class", "homeroom", "lab", "infirmary", "clinic", "library", "stacks",
        "archives", "hallway", "corridor", "room", "bedroom", "dorm", "office",
        "cafeteria", "dining", "gym", "music", "art", "dungeon", "crypt", "cell",
        "tavern", "inn", "bar", "shop", "store", "station", "train", "cathedral",
        "church", "throne", "vault", "interior", "counter", "booth", "den"
    )

    has_outdoor = any(sig in text for sig in outdoor_signals)
    has_indoor = any(sig in text for sig in indoor_signals)

    if has_outdoor and not has_indoor:
        is_indoor = False
    elif has_indoor and not has_outdoor:
        is_indoor = True
    elif "rooftop" in text or "courtyard" in text or "park" in text or "street" in text or "forest" in text:
        is_indoor = False
    else:
        is_indoor = True  # Most narrative scenes take place in rooms

    tags: List[str] = []

    # --- School & Academy Archetypes ---
    if any(k in text for k in ("chemistry", "science lab", "laboratory", "physics lab", "biology lab")):
        tags.extend(["chemistry laboratory", "black resin lab benches", "glassware", "glass beakers", "test tubes in rack", "periodic table on wall", "fume hood", "indoor"])
    elif any(k in text for k in ("infirmary", "nurse", "clinic", "hospital", "ward", "medical")):
        tags.extend(["school infirmary", "medical clinic", "white partition curtains", "clinic bed with white sheets", "bedside table", "medicine cabinet", "indoor"])
    elif any(k in text for k in ("library", "stacks", "archives", "study hall")):
        tags.extend(["grand academy library", "towering wooden bookshelves", "endless rows of books", "polished study tables", "brass reading lamps", "vintage book spines", "indoor"])
    elif any(k in text for k in ("student council", "headmaster", "principal", "faculty office", "executive room")):
        tags.extend(["student council executive room", "polished mahogany conference table", "leather swivel chairs", "official documents", "wall clock", "indoor"])
    elif any(k in text for k in ("music room", "music hall", "band room", "orchestra")):
        tags.extend(["music classroom", "grand piano", "sheet music stands", "acoustic tiered flooring", "soundproof wall panels", "indoor"])
    elif any(k in text for k in ("art room", "atelier", "painting studio")):
        tags.extend(["art classroom", "wooden easels", "canvas paintings", "plaster busts", "paint-stained tables", "art supplies", "indoor"])
    elif any(k in text for k in ("cafeteria", "canteen", "dining hall", "food court")):
        tags.extend(["school cafeteria", "dining tables", "plastic chairs", "meal tray counter", "drink dispensers", "indoor"])
    elif any(k in text for k in ("gymnasium", "gym", "dojo", "sports hall", "basketball court")):
        tags.extend(["school gymnasium", "polished hardwood basketball court", "painted court lines", "folded bleachers", "basketball hoops", "indoor"])
    elif any(k in text for k in ("locker room", "changing room", "shower room")):
        tags.extend(["school locker room", "metal lockers", "wooden changing benches", "duffel bags", "indoor"])
    elif any(k in text for k in ("hallway", "corridor", "stairwell", "passageway")):
        tags.extend(["school hallway", "polished linoleum floor", "rows of lockers", "classroom sliding doors", "bulletin boards with club posters", "indoor"])
    elif any(k in text for k in ("rooftop", "roof")):
        tags.extend(["school rooftop", "chain-link wire fence", "open sky", "ventilation ducts", "concrete floor", "panoramic city view", "outdoor"])
    elif any(k in text for k in ("courtyard", "quad", "campus grounds", "school yard")):
        tags.extend(["academy courtyard", "stone paved walkways", "manicured green lawn", "stone fountain", "park benches", "flowering shrubs", "outdoor"])
    elif any(k in text for k in ("class", "homeroom", "academy", "school")):
        tags.extend(["school classroom", "wooden student desks", "green chalkboard", "large glass windows", "teacher's podium", "lockers at rear", "indoor"])

    # --- Modern & Urban Archetypes ---
    elif any(k in text for k in ("convenience store", "konbini", "mart")):
        tags.extend(["convenience store interior", "brightly lit aisles", "shelves stocked with snacks and drinks", "illuminated beverage coolers", "checkout counter", "indoor"])
    elif any(k in text for k in ("cafe", "coffee shop", "tea house")):
        tags.extend(["cozy cafe", "wooden tables", "espresso machine on counter", "pastry display case", "chalkboard menu", "warm cafe ambiance", "indoor"])
    elif any(k in text for k in ("train station", "station platform", "train tracks")):
        tags.extend(["train station platform", "train tracks", "overhead signage", "yellow safety line", "commuter train", "glass waiting shelter", "outdoor"])
    elif any(k in text for k in ("train interior", "subway car", "metro")):
        tags.extend(["commuter train interior", "overhead hand straps", "cushioned passenger seats", "glass windows with passing city", "indoor"])
    elif any(k in text for k in ("arcade", "game center")):
        tags.extend(["video arcade", "glowing arcade cabinets", "neon lights", "claw machines", "colorful game screens", "indoor"])
    elif any(k in text for k in ("bedroom", "dorm", "apartment", "living room", "personal room")):
        tags.extend(["cozy bedroom", "neatly made bed", "warm duvet", "bedside table", "warm bedside lamp", "wardrobe", "personal study desk", "indoor"])
    elif any(k in text for k in ("street", "sidewalk", "alleyway", "urban street")):
        tags.extend(["city street", "pedestrian sidewalk", "asphalt road", "storefronts", "utility poles and overhead wires", "vending machines", "outdoor"])
    elif any(k in text for k in ("park", "public plaza", "town square", "botanical garden")):
        tags.extend(["city park", "lush green trees", "stone walking path", "park benches", "flowerbeds", "public plaza", "outdoor"])

    # --- Fantasy & Medieval Archetypes ---
    elif any(k in text for k in ("tavern", "inn", "pub", "bar")):
        tags.extend(["fantasy medieval tavern", "sturdy oak tables", "wooden benches", "stone hearth with crackling fire", "ale mugs", "wooden barrels", "iron chandeliers", "indoor"])
    elif any(k in text for k in ("guild hall", "guildhall", "adventurers guild")):
        tags.extend(["adventurers guild hall", "grand wooden counter", "quest notice board with parchment flyers", "weapons mounted on wall", "guild banners", "indoor"])
    elif any(k in text for k in ("dungeon", "crypt", "catacomb", "jail", "cell", "prison")):
        tags.extend(["dark stone dungeon", "ancient mossy masonry", "iron-barred cells", "wall torch brackets", "chains and shackles", "damp cobblestone", "indoor"])
    elif any(k in text for k in ("throne room", "castle", "palace", "grand hall")):
        tags.extend(["grand palace throne room", "soaring vaulted ceiling", "stained glass arched windows", "red velvet carpet", "gilded marble pillars", "ornate chandeliers", "indoor"])
    elif any(k in text for k in ("cathedral", "church", "chapel", "temple", "sanctuary")):
        tags.extend(["gothic cathedral", "towering stained glass windows", "wooden pews", "high stone arches", "altar", "burning votive candles", "indoor"])
    elif any(k in text for k in ("blacksmith", "forge", "armory")):
        tags.extend(["blacksmith forge", "glowing hot coals", "heavy anvil", "forging hammers", "weapon racks", "whetstones", "indoor"])
    elif any(k in text for k in ("alchemy", "apothecary", "herbalist")):
        tags.extend(["alchemy apothecary", "glass flasks with glowing colored potions", "dried herbs hanging from ceiling", "brass scales", "mortar and pestle", "wooden apothecary drawers", "indoor"])
    elif any(k in text for k in ("forest", "woods", "grove", "deepwood")):
        tags.extend(["ancient enchanted forest", "towering moss-covered trees", "winding dirt pathway", "lush ferns", "dense forest canopy", "outdoor"])
    elif any(k in text for k in ("cavern", "cave", "grotto")):
        tags.extend(["natural underground cavern", "jagged stalactites", "glowing crystal formations", "underground pool", "damp rock walls", "indoor"])
    elif any(k in text for k in ("ruins", "shrine", "monument")):
        tags.extend(["ancient stone ruins", "overgrown ivy", "crumbling pillars", "weathered stone altar", "ancient stone engravings", "outdoor"])
    elif any(k in text for k in ("market", "bazaar", "marketplace")):
        tags.extend(["bustling fantasy marketplace", "colorful fabric awnings", "merchant wooden stalls", "crates of fruits and spices", "cobblestone plaza", "outdoor"])

    # --- Cyberpunk & Sci-Fi Archetypes ---
    elif any(k in text for k in ("cyberpunk", "neon alley", "back alley")):
        tags.extend(["cyberpunk neon city", "glowing holographic signs in kanji", "rain-slicked asphalt with reflections", "steam vents", "tangled cables overhead", "outdoor"])
    elif any(k in text for k in ("server room", "data center", "hacker den", "mainframe")):
        tags.extend(["high-tech server room", "glowing LED server racks", "fiber optic cables", "holographic monitor arrays", "terminal consoles", "indoor"])
    elif any(k in text for k in ("spaceship", "bridge", "cockpit", "command deck")):
        tags.extend(["spaceship command bridge", "panoramic starfield viewport", "holographic navigation displays", "glowing instrument consoles", "indoor"])

    # Fallbacks
    else:
        if is_indoor:
            tags.extend(["detailed interior background", "architectural details", "decorative wall moldings", "ambient indoor lighting", "indoor"])
        else:
            tags.extend(["detailed outdoor scenery", "scenic landscape", "horizon view", "open air", "architectural backdrop", "outdoor"])

    return _join_tags(tags), is_indoor


def format_scenery_tags(location: str = "", scene_title: str = "") -> str:
    """Backward-compatible wrapper returning scenery tags for location/scene_title."""
    tags, _ = format_scenery_archetype_tags(location=location, scene_title=scene_title)
    return tags


def format_props_tags(
    props_data: Any,
    focal_point: str = "",
    max_props: int = 3
) -> str:
    """Extracts and formats active interactive room props and focal anchors into Danbooru tags."""
    tags: List[str] = []

    # 1. Focal point anchor
    fp_clean = (focal_point or "").strip().lower()
    if fp_clean:
        if "desk" in fp_clean:
            tags.append("wooden student desk, open textbook, notebook, stationery")
        elif any(k in fp_clean for k in ("podium", "lectern")):
            tags.append("teacher's podium, wooden lectern")
        elif "window" in fp_clean:
            tags.append("standing by window, window frame, curtains")
        elif "bed" in fp_clean:
            tags.append("sitting on bed, duvet, pillows")
        elif "counter" in fp_clean:
            tags.append("at counter, bar stools")
        elif "fountain" in fp_clean:
            tags.append("stone fountain, water basin")
        elif any(k in fp_clean for k in ("railing", "fence")):
            tags.append("at chain-link fence railing")

    # 2. Extract prop names
    extracted_names: List[str] = []
    if isinstance(props_data, dict):
        extracted_names = [str(k) for k in props_data.keys()]
    elif isinstance(props_data, list):
        for item in props_data:
            if isinstance(item, dict) and item.get("name"):
                extracted_names.append(str(item["name"]))
            elif isinstance(item, str) and item.strip():
                extracted_names.append(item.strip())

    PROP_MAPPINGS = {
        "desk": "wooden desks, stationery, scattered papers",
        "chalkboard": "green chalkboard with notes, chalk dust",
        "whiteboard": "whiteboard with markers",
        "bulletin": "cork bulletin board with flyers and club posters",
        "locker": "metal lockers",
        "podium": "teacher's wooden podium",
        "bookshelf": "tall bookshelves with books",
        "books": "stacks of books, open textbook",
        "microscope": "microscope, glassware",
        "flask": "chemical flasks, test tubes",
        "curtain": "fluttering window curtains",
        "bed": "neatly made bed, white sheets",
        "couch": "leather sofa",
        "sofa": "leather sofa",
        "hearth": "stone fireplace, crackling fire",
        "fireplace": "stone fireplace, fire",
        "torch": "flickering wall torches",
        "candle": "glowing candles, candelabra",
        "mug": "wooden mugs, ale tankards",
        "piano": "grand piano",
        "easel": "wooden art easel, canvas",
        "barrel": "wooden barrels",
        "crate": "wooden storage crates",
        "fountain": "carved stone fountain",
        "bench": "wooden park bench",
        "statue": "carved stone statue",
        "altar": "stone ritual altar",
        "cage": "iron-barred cage",
        "shackle": "chains and shackles",
        "terminal": "glowing computer terminal, monitor",
        "server": "server rack with flashing LED lights",
        "vending": "illuminated vending machines",
    }

    added_count = 0
    for name in extracted_names:
        if added_count >= max_props:
            break
        nl = name.lower()
        if any(ign in nl for ign in ("entrance", "door", "exit", "cubbies", "hall")):
            continue
        matched_tag = None
        for kw, tag in PROP_MAPPINGS.items():
            if kw in nl:
                matched_tag = tag
                break
        if matched_tag and matched_tag not in tags:
            tags.append(matched_tag)
            added_count += 1
        elif not matched_tag and len(nl) < 25 and added_count < max_props:
            clean_p = _clean_tag(nl.replace("the ", "").replace("a ", ""))
            if clean_p and clean_p not in tags:
                tags.append(clean_p)
                added_count += 1

    return _join_tags(tags)


def format_weather_and_atmosphere_tags(
    session: Dict[str, Any],
    outcome: Dict[str, Any],
    is_indoor: bool,
    time_phase: str
) -> str:
    """Extracts weather, seasonal cues, and ambient atmospheric particles."""
    tags: List[str] = []
    text_corpus = f"{outcome.get('scene_title', '')} {outcome.get('narrative', '')} {session.get('weather', '')} {session.get('season', '')}".lower()

    if "rain" in text_corpus:
        if is_indoor:
            tags.append("rain, raindrops on window, rain reflections on glass, wet windowsill, moody rain atmosphere")
        else:
            tags.append("rain, falling raindrops, wet pavement, puddles with reflections, overcast sky")
    elif "snow" in text_corpus:
        if is_indoor:
            tags.append("frost on window glass, snow outside window, winter chill, cozy warm indoor")
        else:
            tags.append("falling snowflakes, snow covered ground, winter atmosphere, cold breath, overcast winter sky")
    elif "spring" in text_corpus or "sakura" in text_corpus or "cherry blossom" in text_corpus:
        tags.append("falling cherry blossom petals, sakura petals drifting, gentle spring breeze")
    elif "autumn" in text_corpus or "fall" in text_corpus:
        tags.append("falling autumn leaves, golden ginkgo leaves, crisp autumn air")
    else:
        # Default scenario ambient particles
        scen = str(session.get("scenario", "")).lower()
        if "fantasy" in scen:
            tags.append("floating glowing motes, subtle light particles")
        elif "cyber" in scen:
            tags.append("neon glow reflections, faint steam, futuristic haze")
        elif is_indoor and time_phase in ("Morning", "Afternoon", "Early Morning"):
            tags.append("floating dust motes in sunlight, soft light rays")
        elif not is_indoor:
            tags.append("gentle breeze, tranquil air")

    return _join_tags(tags)


def format_mood_tags(
    action: Dict[str, Any],
    outcome: Dict[str, Any],
    is_intimate: bool = False,
    is_combat: bool = False
) -> str:
    """Maps turn action, emotional intent, and check tier to visual mood and lighting tone."""
    if is_intimate:
        return "intimate atmosphere, romantic mood, soft warm lighting, delicate highlights, dreamy ambiance"
    if is_combat:
        return "dynamic lighting, dramatic high-contrast shadows, intense atmosphere, action scene, sparks, cinematic tension"

    intent = str(action.get("intent") or "").lower()
    if intent in ("stealth_covert", "eavesdrop", "pickpocket", "hide"):
        return "dim lighting, deep shadows, moody chiaroscuro, suspenseful atmosphere, muted colors"

    check = action.get("check")
    tier = getattr(check, "tier", None) or (check.get("tier") if isinstance(check, dict) else None) or action.get("tier", "")
    tier_clean = str(tier).lower()
    if "crit_success" in tier_clean or "crit_pass" in tier_clean:
        return "warm radiant lighting, cheerful atmosphere, bright highlights, uplifting mood"
    if "crit_fail" in tier_clean:
        return "dramatic shadows, high contrast, tense atmosphere, cinematic gloom"

    return "peaceful atmosphere, clean lighting, clear details"


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
    Dynamically blends location archetype, active room props, time-of-day clock lighting,
    weather particles, and atmospheric mood.
    """
    outcome = outcome or {}
    action = action or {}
    session_id = session.get("id") or 0
    scen_key = session.get("scenario", "fantasy")
    style_tags = SCENARIO_STYLE_TOKENS.get(scen_key, DEFAULT_STYLE_TOKENS)

    # 1. Spatial Location & Archetype
    location = outcome.get("location") or session.get("current_location") or ""
    scene_title = outcome.get("scene_title") or session.get("scene_title") or ""
    focal_point = outcome.get("focal_point") or session.get("focal_point") or ""
    scenery_archetype_tags, is_indoor = format_scenery_archetype_tags(
        location=location,
        scene_title=scene_title,
        scenario=scen_key
    )

    # 2. In-Game 24-Hour Clock & Lighting
    curr_min = outcome.get("current_minute") or session.get("current_minute")
    time_desc = str(outcome.get("time_of_day") or session.get("time_of_day") or session.get("formatted_time") or "")
    time_lighting_tags, time_phase = format_time_lighting_tags(
        minute=curr_min,
        is_indoor=is_indoor,
        time_desc=time_desc
    )

    # 3. Active Room Props & Focal Anchors
    physical_state = outcome.get("_physical_state") or session.get("physical_state") or {}
    raw_props = outcome.get("props") or (physical_state.get("props") if isinstance(physical_state, dict) else None) or session.get("props")
    props_tags = format_props_tags(props_data=raw_props, focal_point=focal_point, max_props=3)

    # 4. Weather, Seasonal Particles & Atmospheric Dust
    weather_tags = format_weather_and_atmosphere_tags(
        session=session,
        outcome=outcome,
        is_indoor=is_indoor,
        time_phase=time_phase
    )

    # 5. Scene Emotional Mood & Lighting Highlights
    act_intent = str(action.get("intent") or "").lower()
    act_sub_intent = str(action.get("sub_intent") or "").lower()
    is_intimate = (
        act_intent == "intimate_act"
        or any(k in act_sub_intent for k in ("kiss", "foreplay", "oral", "intercourse", "aftercare"))
        or bool(outcome.get("intimate_update"))
    )
    nearby_enemies = outcome.get("nearby_enemies") or session.get("nearby_enemies") or []
    mood_tags = format_mood_tags(
        action=action,
        outcome=outcome,
        is_intimate=is_intimate,
        is_combat=bool(nearby_enemies)
    )

    # 6. Authored Starting Hook Visual Cues
    opening_cues = str(outcome.get("visual_cues") or session.get("opening_visual_cues") or "").strip()

    # Full Combined Environmental Block
    environment_tags = _join_tags(
        scenery_archetype_tags,
        props_tags,
        time_lighting_tags,
        weather_tags,
        mood_tags,
        opening_cues
    )

    # 7. Check tier & Action Context
    check = action.get("check")
    check_tier = getattr(check, "tier", None) or (check.get("tier") if isinstance(check, dict) else None) or action.get("tier", "")

    # Combat Check (Monster / Enemy Confrontation)
    if nearby_enemies:
        enemy = nearby_enemies[0]
        e_name = enemy.get("name", "Enemy") if isinstance(enemy, dict) else str(enemy)
        e_species = _clean_tag(e_name.replace("Warrior", "").replace("Scout", "").replace("Leader", ""))
        combat_camera = "dynamic combat angle, medium shot, action camera, dramatic depth of field, key visual"
        combat_prompt = _join_tags(
            BASE_QUALITY_TOKENS,
            style_tags,
            "1monster, combat scene, battle stance",
            f"{e_species}, glowing eyes, aggressive expression, snarling",
            "wielding weapon, action pose",
            combat_camera,
            environment_tags
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
    raw_npc_names: List[str] = []

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
    actor_clothes = physical_state.get("actors", {}) if isinstance(physical_state, dict) else {}

    # Case 0: No NPCs present -> Pure Scenery (Wide)
    if not valid_npcs:
        camera_tags = "wide angle, landscape orientation, establishing shot, highly detailed environment, depth of field, atmospheric perspective, rich architectural details, key visual"
        scene_prompt = _join_tags(
            BASE_QUALITY_TOKENS,
            style_tags,
            "scenery, no humans, landscape",
            environment_tags,
            camera_tags
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
        pose_tags = format_pose_tags(actor_poses.get(focal_name, {}), location=location, focal_point=focal_point)
        camera_tags = "medium shot, upper body, facing viewer, eye level, looking at viewer, shallow depth of field, blurry background, bokeh, cinematic lighting, key visual"

        solo_prompt = _join_tags(
            BASE_QUALITY_TOKENS,
            style_tags,
            gender_tag,
            app_tags,
            expr_tags,
            pose_tags,
            camera_tags,
            environment_tags
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
    pose1 = format_pose_tags(actor_poses.get(npc1_name, {}), location=location, focal_point=focal_point)
    pose2 = format_pose_tags(actor_poses.get(npc2_name, {}), location=location, focal_point=focal_point)

    camera_tags = "talking to each other, medium shot, cowboy shot, shallow depth of field, slight bokeh, cinematic composition, key visual"
    extra_ambient = "students in background, ambient crowd" if len(valid_npcs) > 2 else ""

    header_tags = _join_tags(
        BASE_QUALITY_TOKENS,
        style_tags,
        count_tag,
        camera_tags,
        environment_tags,
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
