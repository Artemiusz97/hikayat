from __future__ import annotations
from .constants import (
    ASSET_SIZE_TIERS,
    FEMALE_ASSET_TEXTURE_TEMPLATES,
    MALE_ASSET_TEXTURE_TEMPLATES,
    SPECIES_TEXTURE_AFFINITIES,
    TIER_INCOMPATIBLE_TEXTURES,
)
from .constants import *
import json
import hashlib
import random
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
    if not m_eye:
        m_eye = re.search(
            r"\beyes?\s+(?:were|was|of)\s+(?:a\s+|an\s+)?(piercing amber|smoldering amber|amber|burning gold|golden|molten gold|gold|ice blue|sapphire blue|blue|emerald green|jade green|green|hazel|chestnut|ruby red|ruby|violet|amethyst|topaz|grey|gray|dark slate|copper)\b",
            target,
            re.IGNORECASE
        )
    if m_eye:
        extracted["eye_color"] = m_eye.group(1).lower().replace(" ", "_")

    # 2. Stature
    m_stat = re.search(
        r"\b(miniature|dwarf|diminutive|below[\s\-_]average|short|petite|compact|average[\s\-_]height|average|tall|towering|gigantic|statuesque)\b",
        target,
        re.IGNORECASE
    )
    if m_stat:
        extracted["stature"] = normalize_stature_tier(m_stat.group(1))

    # 3. Coat / Fur / Scales
    _coat_col_pat = r"((?:(?:vibrant|pastel|shimmering|glistening|sleek|velvety|dense|silky|soft|fluffy|deep|light|dark|bright|pale|iridescent|radiant|electric|neon)\s+)?(?:[a-z]+[\-_])?(?:snow[\s\-_]white|pure[\s\-_]white|white|midnight[\s\-_]black|jet[\s\-_]black|black|ash[\s\-_]gray|silver[\s\-_]white|frost[\s\-_]white|golden[\s\-_]amber|golden|gold|rust[\s\-_]red|tawny|chestnut|charcoal|fawn|cream|calico|spotted|striped|cerulean|azure|cobalt|sapphire|cyan|sky[\s\-_]blue|blue|sakura[\s\-_]pink|bubblegum|magenta|rose|pink|amethyst|lavender|violet|lilac|purple|emerald|jade|mint[\s\-_]green|mint|olive|forest[\s\-_]green|seafoam|sage|green|crimson|ruby|scarlet|copper|amber|orange|flame|red|blonde|silver|bronze|turquoise|coral|peach|caramel|cocoa)(?:[\s\-_](?!and\b|with\b|while\b|but\b|her\b|his\b|their\b|whose\b|also\b|or\b)[a-z]+)?)"
    m_coat = re.search(
        rf"\b{_coat_col_pat}\s+(fur|coat|scales?|feathers?)\b",
        target,
        re.IGNORECASE
    )
    if not m_coat:
        m_coat_rev = re.search(
            rf"\b(fur|coat|scales?|feathers?)\s+(?:(?:was|is)\s+)?(?:of\s+|a\s+|an\s+)?{_coat_col_pat}\b",
            target,
            re.IGNORECASE
        )
        if m_coat_rev:
            c_type = m_coat_rev.group(1).lower()
            c_col = m_coat_rev.group(2).lower()
            extracted["coat_color"] = f"{c_col} {c_type}"
            if "scale" in c_type:
                extracted["skin_type"] = "scaly"
            elif "feather" in c_type:
                extracted["skin_type"] = "feathered"
            elif "fur" in c_type:
                extracted["skin_type"] = "furry"
    else:
        extracted["coat_color"] = f"{m_coat.group(1).lower()} {m_coat.group(2).lower()}"
        if "scale" in m_coat.group(2).lower():
            extracted["skin_type"] = "scaly"
        elif "feather" in m_coat.group(2).lower():
            extracted["skin_type"] = "feathered"
        elif "fur" in m_coat.group(2).lower():
            extracted["skin_type"] = "furry"

    # 4. Skin / Complexion (for Humanoids)
    m_skin = re.search(
        r"\b((?:fair|pale|porcelain|tan|tanned|sun[\s\-_]kissed|olive|bronze|dark|deep|rich|warm\s+honey|ebony|golden)\s+(?:skin|complexion))\b",
        target,
        re.IGNORECASE
    )
    if not m_skin:
        m_skin_rev = re.search(
            r"\b(?:skin|complexion)\s+(?:was|is|of)\s+(?:a\s+|an\s+)?(fair|pale|porcelain|tan|tanned|sun[\s\-_]kissed|olive|bronze|dark|deep|rich|warm\s+honey|ebony|golden)\b",
            target,
            re.IGNORECASE
        )
        if m_skin_rev:
            extracted["skin_color"] = f"{m_skin_rev.group(1).lower()} skin"
    else:
        extracted["skin_color"] = m_skin.group(1).lower()

    # 5. Hair
    _hair_col_pat = r"((?:(?:vibrant|pastel|electric|neon|shimmering|soft|silky|sleek|deep|light|dark|bright|pale)\s+)?(?:[a-z]+[\-_])?(?:snow[\s\-_]white|platinum|golden[\s\-_]blonde|blonde|black|dark[\s\-_]slate|auburn|chestnut|brown|silver|cerulean|azure|cyan|sky[\s\-_]blue|blue|sakura[\s\-_]pink|bubblegum|magenta|rose|pink|amethyst|lavender|violet|lilac|purple|emerald|jade|mint[\s\-_]green|mint|olive|forest[\s\-_]green|seafoam|sage|green|crimson|ruby|scarlet|copper|amber|orange|flame|red|gold)(?:[\s\-_](?!and\b|with\b|while\b|but\b|her\b|his\b|their\b|whose\b|also\b|or\b)[a-z]+)?)"
    m_hair = re.search(
        rf"\b{_hair_col_pat}\s+hair\b",
        target,
        re.IGNORECASE
    )
    if not m_hair:
        m_hair_rev = re.search(
            rf"\bhair\s+(?:(?:was|is)\s+)?(?:dyed|colored|tinted|was|is)\s+(?:a\s+|an\s+)?{_hair_col_pat}\b",
            target,
            re.IGNORECASE
        )
        if m_hair_rev:
            extracted["hair_color"] = m_hair_rev.group(1).lower()
            if "dyed" in target.lower():
                extracted["is_dyed"] = True
    else:
        extracted["hair_color"] = m_hair.group(1).lower()
        if re.search(r"\bdyed\s+(?:to\s+|a\s+|an\s+)?" + re.escape(m_hair.group(1)), target, re.IGNORECASE):
            extracted["is_dyed"] = True

    return extracted


def classify_asset_size_tier(size_str: str, gender: str = "female") -> str:
    """Classifies anatomy size string into one of 5 canonical tiers:
    'flat', 'small', 'average', 'large', 'huge'.
    """
    if not size_str or not isinstance(size_str, str):
        return "average"
    s_low = size_str.lower().strip()

    is_male = any(kw in str(gender).lower() for kw in ("male", "man", "boy")) and "female" not in str(gender).lower()

    if is_male:
        inch_explicit = re.search(r'(\d+(?:\.\d+)?)\s*(?:\"|inch)', s_low)
        if inch_explicit:
            try:
                val = float(inch_explicit.group(1))
                if val < 4.5:
                    return "small" if val >= 3.5 else "flat"
                if val < 6.0:
                    return "average"
                if val < 8.0:
                    return "large"
                return "huge"
            except ValueError:
                pass

        if any(w in s_low for w in ("tiny", "micro", "very small", "puny", "barely")):
            return "flat"
        if any(w in s_low for w in ("small", "modest", "compact", "petite", "below average", "slender & ultra-sensitive")):
            return "small"
        if any(w in s_low for w in ("huge", "massive", "enormous", "gigantic", "hyper", "colossal", "dense & formidable")):
            return "huge"
        if any(w in s_low for w in ("large", "thick", "above average", "heavy", "big", "generous", "formidable")):
            return "large"
        return "average"
    else:
        # Female breasts: cup letters take absolute precedence
        if re.search(r'\b(aa|aaa)(?:\+)?-cup\b', s_low) or any(w in s_low for w in ("almost flat", "barely there")):
            return "flat"
        if re.search(r'\b([e-h]+(?:\+)?-cup)\b', s_low) or any(w in s_low for w in ("huge", "massive", "hyper", "bountiful e", "bountiful", "gigantic")):
            return "huge"
        if re.search(r'\b(d{1,3}(?:\+)?-cup)\b', s_low) or any(w in s_low for w in ("voluptuous d", "generous dd", "full d", "heavy d", "busty", "stacked", "voluptuous")):
            return "large"
        if re.search(r'\b(c(?:\+)?-cup)\b', s_low) or any(w in s_low for w in ("shapely c", "full c", "toned c", "proportional", "moderate")):
            return "average"
        if re.search(r'\b([ab](?:\+)?-cup)\b', s_low) or any(w in s_low for w in ("modest b", "perky b", "soft a")):
            return "small"
        if any(w in s_low for w in ("flat", "tiny", "barely")):
            return "flat"
        if any(w in s_low for w in ("large", "heavy")):
            return "large"
        if any(w in s_low for w in ("small", "petite", "modest", "perky", "slender")):
            return "small"
        return "average"


def extract_asset_texture(size_str: str, gender: str = "female") -> str:
    """Extracts known tactile/shape trait from a compound size string (e.g. 'Soft A-Cup' -> 'Tender & Delicate')."""
    if not size_str or not isinstance(size_str, str):
        return ""
    s_low = size_str.lower().strip()
    is_male = any(kw in str(gender).lower() for kw in ("male", "man", "boy")) and "female" not in str(gender).lower()
    templates = MALE_ASSET_TEXTURE_TEMPLATES if is_male else FEMALE_ASSET_TEXTURE_TEMPLATES

    for t in templates:
        if t.lower() in s_low:
            return t
        t_first = t.split("&")[0].strip().lower()
        if len(t_first.split()) >= 2 and t_first in s_low:
            return t

    # Fuzzy & flaring keyword mappings
    if "perky" in s_low:
        return "Perky & High-Set"
    if "fluffy" in s_low or "chest fur" in s_low or "fur-rimmed" in s_low:
        return "Soft & Downy Chest Fur"
    if "fur" in s_low:
        return "Soft Fur-Ringed Base" if is_male else "Soft & Downy Chest Fur"
    if "firm" in s_low:
        return "Veined & Firm" if is_male else "Firm & Toned"
    if "pillowy" in s_low or "yielding" in s_low:
        return "Pillowy Soft & Yielding"
    if "soft" in s_low:
        if not is_male:
            tier = classify_asset_size_tier(size_str, gender="female")
            return "Tender & Delicate" if tier in ("flat", "small") else "Pillowy Soft & Yielding"
        return "Smooth & Supple"
    if "veined" in s_low:
        return "Veined & Firm"
    if "pulsing" in s_low:
        return "Warm & Pulsing"
    if "micro-scale" in s_low or "scale" in s_low:
        return "Sleek Scaled Base & Firm" if is_male else "Silky Warm with Smooth Micro-Scales"
    if "feather" in s_low:
        return "Downy Feather-Lined"
    if "plumage" in s_low:
        return "Velvety Plumage Accents"
    if "bouncy" in s_low:
        return "Bouncy & Sensitive"
    if "heavy" in s_low or "plush" in s_low:
        return "Smooth & Heavy" if is_male else "Heavy & Plush"
    if "delicate" in s_low or "tender" in s_low:
        return "Tender & Delicate"
    if "teardrop" in s_low:
        return "Shapely Teardrop"
    if "compact" in s_low or "dense" in s_low:
        return "Dense & Formidable" if is_male else "Compact & Dense"
    if "responsive" in s_low or "sensitive" in s_low:
        return "Slender & Ultra-Sensitive" if is_male else "Sensitive & Responsive"
    if "athletic" in s_low:
        return "Toned & Athletic"
    if "draconic" in s_low or "drake" in s_low:
        return "Sturdy Draconic Build" if is_male else "Sleek & Supple Drake-Contour"
    return ""


def fuse_asset_size_and_texture(size_str: str, texture_str: str, gender: str = "female") -> str:
    """Combines a base size string and a tactile texture trait into a seamless, natural
    compound narrative phrase without parentheses (e.g. 'Bouncy & Sensitive DD-Cup', 'Veined & Firm 7.5"').
    """
    s = str(size_str or "").strip()
    t = str(texture_str or "").strip()
    if not s and not t:
        return ""
    if not t:
        return s
    if not s:
        return t

    # Strip outer parentheses if already present
    s = re.sub(r'^\((.*?)\)$', r'\1', s).strip()
    t = re.sub(r'^\((.*?)\)$', r'\1', t).strip()

    is_male = any(kw in str(gender).lower() for kw in ("male", "man", "boy")) and "female" not in str(gender).lower()

    # If s already contains the texture (or substantial part of it), avoid duplication
    t_clean = t.replace("&", "").strip().lower()
    s_clean = s.replace("&", "").strip().lower()
    if t.lower() in s.lower() or (len(t_clean) > 3 and t_clean in s_clean):
        return s

    if not is_male:
        # Female breasts: look for cup pattern like 'AA-Cup', 'DD-Cup', 'B-Cup', etc.
        cup_match = re.search(r'\b([A-Ha-h]+(?:\+)?-Cup)\b', s, re.IGNORECASE)
        if cup_match:
            cup_part = cup_match.group(1).upper()
            if cup_part.endswith("-CUP"):
                cup_part = cup_part[:-4] + "-Cup"
            return f"{t} {cup_part}"

        # If s mentions 'flat' or 'barely'
        if any(w in s.lower() for w in ("flat", "barely")):
            if "flat" not in t.lower():
                return f"{t} Flat Chest"
            return t

        # Strip generic redundant adjectives like 'Generous', 'Voluptuous', 'Modest', 'Petite'
        redundant_prefixes = {
            "generous", "voluptuous", "modest", "petite", "heavy", "bountiful",
            "shapely", "toned", "firm", "soft", "full", "small", "large", "average"
        }
        words = s.split()
        filtered_words = [w for w in words if w.lower() not in redundant_prefixes]
        base_remainder = " ".join(filtered_words).strip()
        if base_remainder:
            return f"{t} {base_remainder}"
        return f"{t} {s}"
    else:
        # Male anatomy: look for inch measurement e.g. 7.5", 8", 6.5 inches
        inch_match = re.search(r'(\d+(?:\.\d+)?\s*(?:\"|inch(?:es)?))', s, re.IGNORECASE)
        if inch_match:
            inch_part = inch_match.group(1).strip()
            if "inch" in inch_part.lower():
                val = re.findall(r'\d+(?:\.\d+)?', inch_part)[0]
                inch_part = f'{val}"'
            return f"{t} {inch_part}"

        redundant_prefixes = {
            "thick", "long", "massive", "compact", "slender", "sturdy",
            "dense", "toned", "formidable", "large", "huge", "small"
        }
        words = s.split()
        filtered_words = [w for w in words if w.lower() not in redundant_prefixes]
        base_remainder = " ".join(filtered_words).strip()
        if base_remainder:
            return f"{t} {base_remainder}"
        return f"{t} {s}"


def roll_dynamic_asset_texture(
    seed_val: Any = 0,
    gender: str = "female",
    race: str = "human",
    physique: str = "",
    demeanor: str = "",
    size_tier: str = "average",
    seed: Any = None,
) -> str:
    """Rolls a tactile texture/shape trait from the open template pool with a +20% weighted
    synergy boost for matching criteria, strictly filtering out tier-incompatible traits.
    """
    raw_seed = seed if seed is not None else seed_val
    if isinstance(raw_seed, str):
        try:
            effective_seed = int(raw_seed)
        except ValueError:
            effective_seed = int(hashlib.md5(raw_seed.encode("utf-8")).hexdigest()[:8], 16)
    else:
        try:
            effective_seed = int(raw_seed)
        except (ValueError, TypeError):
            effective_seed = 0

    is_male = any(kw in str(gender).lower() for kw in ("male", "man", "boy")) and "female" not in str(gender).lower()
    pool = list(MALE_ASSET_TEXTURE_TEMPLATES if is_male else FEMALE_ASSET_TEXTURE_TEMPLATES)

    # 1. Apply tier incompatibility exclusion filter
    incompat = TIER_INCOMPATIBLE_TEXTURES.get(size_tier, set())
    candidate_pool = [t for t in pool if t not in incompat]
    if not candidate_pool:
        candidate_pool = pool

    # 2. Identify synergies for the 20% weight boost
    r_low = str(race or "").lower()
    p_low = str(physique or "").lower()
    d_low = str(demeanor or "").lower()

    synergy_candidates = set()
    if any(k in r_low for k in ("fox", "cat", "wolf", "neko", "kitsune", "rabbit", "bunny", "tiger", "lion", "bear", "mouse", "beastfolk", "beast")):
        synergy_candidates.update(SPECIES_TEXTURE_AFFINITIES.get("furred", []))
    if any(k in r_low for k in ("reptile", "dragon", "snake", "lizard", "draconic", "scaly")):
        synergy_candidates.update(SPECIES_TEXTURE_AFFINITIES.get("scaled", []))
    if any(k in r_low for k in ("bird", "avian", "harpy", "feathered", "angel")):
        synergy_candidates.update(SPECIES_TEXTURE_AFFINITIES.get("feathered", []))
    if any(k in r_low for k in ("aquatic", "merfolk", "siren", "fish")):
        synergy_candidates.update(SPECIES_TEXTURE_AFFINITIES.get("aquatic", []))

    if any(k in p_low for k in ("toned", "athletic", "muscular", "lean", "fit")):
        synergy_candidates.update(SPECIES_TEXTURE_AFFINITIES.get("athletic", []))
    if any(k in p_low for k in ("voluptuous", "curvy", "busty", "full-figured", "stacked", "hourglass")):
        synergy_candidates.update(SPECIES_TEXTURE_AFFINITIES.get("voluptuous", []))

    # 3. Construct weights (Base = 10; Synergy = 12, a +20% boost)
    weights = []
    for item in candidate_pool:
        w = 12 if item in synergy_candidates else 10
        weights.append(w)

    total_weight = sum(weights)
    if total_weight <= 0:
        return candidate_pool[abs(effective_seed) % len(candidate_pool)]

    pick_val = abs(effective_seed) % total_weight
    cumulative = 0
    for item, w in zip(candidate_pool, weights):
        cumulative += w
        if pick_val < cumulative:
            return item
def normalize_stature_tier(stature_str: str) -> str:
    """Normalizes any stature descriptor or legacy alias into one of the 6 canonical tiers:
    'miniature', 'short', 'below_average', 'average', 'tall', 'towering'.
    """
    s = (stature_str or "").strip().lower().replace("-", "_").replace(" ", "_")
    if s in ("miniature", "dwarf", "dwarven", "halfling", "gnome", "goblin", "diminutive", "tiny", "pint_sized"):
        return "miniature"
    if s in ("petite", "short", "compact", "small"):
        return "short"
    if s in ("below_average", "below", "shortish", "short_average"):
        return "below_average"
    if s in ("towering", "gigantic", "towering_gigantic", "giant", "huge", "colossal"):
        return "towering"
    if s in ("tall", "statuesque", "high"):
        return "tall"
    if s in ("average", "moderate", "medium", "normal"):
        return "average"
    if "miniature" in s or "diminutive" in s or "dwarf" in s or "halfling" in s or "gnome" in s:
        return "miniature"
    if "below" in s:
        return "below_average"
    if "tower" in s or "gigan" in s:
        return "towering"
    if "tall" in s:
        return "tall"
    if "short" in s or "petite" in s:
        return "short"
    return "average"


def get_stature_distribution_for_race(race_str: str, gender: str = "") -> Dict[str, float]:
    """Returns the 6-tier probability distribution dictionary for a given race or species and gender.
    - Miniature races (dwarf, gnome, halfling, goblin): 100% miniature for both genders.
    - Male Standard Races & Medium Beastfolk (Default): 5% short, 15% below_avg, 50% avg, 25% tall, 5% towering.
    - Female Standard Races & Medium Beastfolk (Default): 10% short, 34% below_avg, 45% avg, 10% tall, 1% towering.
    - Male Large Beastfolk & Strong Races: 1% short, 4% below_avg, 25% avg, 45% tall, 25% towering.
    - Female Large Beastfolk & Strong Races: 1% short, 14% below_avg, 55% avg, 20% tall, 10% towering.
    - Male Small Agile Beastfolk: 10% short, 30% below_avg, 43% avg, 15% tall, 2% towering.
    - Female Small Agile Beastfolk: 15% short, 45% below_avg, 34% avg, 5% tall, 1% towering.
    - Male Tiny Beastfolk: 34% short, 45% below_avg, 15% avg, 5% tall, 1% towering.
    - Female Tiny Beastfolk: 55% short, 35% below_avg, 7% avg, 2% tall, 1% towering.
    """
    r = (race_str or "human").strip().lower()
    g = (gender or "").strip().lower()
    is_male = any(kw in g for kw in ("male", "man", "boy", "lord", "he", "him", "his")) and not any(kw in g for kw in ("female", "woman", "girl", "lady", "she", "her"))
    is_fem = any(kw in g for kw in ("female", "woman", "girl", "lady", "she", "her")) or (not is_male and ("fem" in g or g.startswith("f")))

    # 1. Miniature Fantasy Species (strictly miniature for both genders)
    if any(k in r for k in ("dwarf", "gnome", "halfling", "goblin", "kobold", "pixie", "fairy")):
        return dict(STATURE_WEIGHTS_MINIATURE)

    # 2. Hybrids / Half-Beast default to Standard
    if "half" in r or "hybrid" in r:
        return dict(STATURE_WEIGHTS_FEMALE_STANDARD if is_fem else STATURE_WEIGHTS_MALE_STANDARD)

    # 3. Tiny/Smallest Beastfolk (rabbit, mouse, etc.)
    if any(k in r for k in ("rabbit", "bunny", "mouse", "rat", "hamster", "squirrel", "hedgehog")):
        return dict(STATURE_WEIGHTS_FEMALE_TINY_BEASTFOLK if is_fem else STATURE_WEIGHTS_MALE_TINY_BEASTFOLK)

    # 4. Small Agile Beastfolk (cat, fox, fennec, etc.)
    if any(k in r for k in ("cat", "neko", "fox", "kitsune", "fennec", "ferret", "weasel")):
        return dict(STATURE_WEIGHTS_FEMALE_SMALL_BEASTFOLK if is_fem else STATURE_WEIGHTS_MALE_SMALL_BEASTFOLK)

    # 5. Cheetah and similarly sized medium species (same as standard race)
    if "cheetah" in r:
        return dict(STATURE_WEIGHTS_FEMALE_STANDARD if is_fem else STATURE_WEIGHTS_MALE_STANDARD)

    # 6. Large Beastfolk (wolf, tiger, lion, bear, dragon, orc, etc.)
    if any((bool(re.search(r"\box(en)?\b", r)) if k == "ox" else k in r) for k in ("wolf", "tiger", "lion", "bear", "dragon", "orc", "minotaur", "rhino", "elephant", "ox", "boar", "bovine")):
        return dict(STATURE_WEIGHTS_FEMALE_LARGE_BEASTFOLK if is_fem else STATURE_WEIGHTS_MALE_LARGE_BEASTFOLK)

    # 7. Standard Races (human, elf, default)
    return dict(STATURE_WEIGHTS_FEMALE_STANDARD if is_fem else STATURE_WEIGHTS_MALE_STANDARD)


def roll_dynamic_stature(race: str = "", gender: str = "", seed: Any = None) -> str:
    """Rolls a canonical 6-tier stature based on species- and gender-weighted distribution.
    Deterministic if seed is provided.
    """
    dist = get_stature_distribution_for_race(race, gender=gender)
    if dist.get("miniature", 0.0) >= 0.999:
        return "miniature"
    if dist.get("short", 0.0) >= 0.999:
        return "short"

    if seed is not None:
        seed_bytes = f"stature_{seed}_{race}_{gender}".encode("utf-8")
        h = hashlib.md5(seed_bytes).hexdigest()
        roll = (int(h[:8], 16) % 100000) / 100000.0
    else:
        roll = random.random()

    cumulative = 0.0
    for tier in STATURE_TIERS:
        cumulative += dist.get(tier, 0.0)
        if roll <= cumulative:
            return tier
    return "average"


def roll_dynamic_physique(
    gender: str = "female",
    stature: str = "average",
    race: str = "",
    seed: Any = None
) -> str:
    """Rolls a height- and race-aware physique template.
    - Decoupled from height names (e.g. 'Muscular & Powerful').
    - Height-aware: tall/towering cannot be petite; short/below-average favors petite/soft; tall favors slender.
    - Race-aware: large beastfolk favor toned/muscular; small beastfolk favor petite/soft.
    - Thick and overweight physiques have a low baseline roll chance.
    - All non-incompatible physiques remain rollable via probabilistic variance.
    """
    raw_g = (gender or "female").strip().lower()
    is_male = any(kw in raw_g for kw in ("male", "man", "boy", "lord", "he", "him", "his")) and not any(kw in raw_g for kw in ("female", "woman"))

    pool = list(PHYSIQUE_MALE_TEMPLATES if is_male else PHYSIQUE_FEMALE_TEMPLATES)

    # 1. Compatibility filter (tall/towering cannot be petite)
    norm_stature = normalize_stature_tier(stature)
    incompatible = STATURE_INCOMPATIBLE_PHYSIQUES.get(norm_stature, set())
    candidates = [p for p in pool if p not in incompatible]

    # 2. Base weights (thick & overweight have low chance rates)
    weights = {}
    for p in candidates:
        if p in ("Thick & Curvy", "Stocky & Thick"):
            weights[p] = 0.35  # Low chance rate for thick
        elif p in ("Soft & Overweight", "Heavy & Overweight"):
            weights[p] = 0.15  # Low chance rate for overweight
        else:
            weights[p] = 1.0   # Standard baseline

    # 3. Stature modifiers
    if norm_stature in ("miniature", "short", "below_average"):
        if "Petite & Soft" in weights:
            weights["Petite & Soft"] *= 2.0
        if "Soft & Curved" in weights:
            weights["Soft & Curved"] *= 1.3
        if "Stocky & Thick" in weights:
            weights["Stocky & Thick"] *= 1.3
    elif norm_stature in ("tall", "towering"):
        if "Hourglass & Slender" in weights:
            weights["Hourglass & Slender"] *= 1.8
        if "Slender & Lanky" in weights:
            weights["Slender & Lanky"] *= 1.8
        if "Broad Shoulders & Lean" in weights:
            weights["Broad Shoulders & Lean"] *= 1.4
        if "Muscular & Powerful" in weights:
            weights["Muscular & Powerful"] *= 1.3

    # 4. Race modifiers
    r = (race or "").lower()
    if "dwarf" in r:
        if "Stocky & Thick" in weights:
            weights["Stocky & Thick"] *= 2.2
        if "Muscular & Powerful" in weights:
            weights["Muscular & Powerful"] *= 1.8
    is_small_beast = any(k in r for k in ("cat", "neko", "fox", "kitsune", "fennec", "rabbit", "bunny", "mouse", "rat", "hamster", "squirrel"))
    is_large_beast = not is_small_beast and any((bool(re.search(r"\box(en)?\b", r)) if k == "ox" else k in r) for k in ("wolf", "tiger", "lion", "bear", "dragon", "orc", "minotaur", "rhino", "elephant", "ox", "boar", "bovine"))

    if is_large_beast:
        if "Toned & Athletic" in weights:
            weights["Toned & Athletic"] *= 1.6
        if "Muscular & Powerful" in weights:
            weights["Muscular & Powerful"] *= 1.8
        if "Full-Figured & Voluptuous" in weights:
            weights["Full-Figured & Voluptuous"] *= 1.3
        if "Stocky & Thick" in weights:
            weights["Stocky & Thick"] *= 1.4
    elif is_small_beast:
        if "Petite & Soft" in weights:
            weights["Petite & Soft"] *= 1.6
        if "Soft & Curved" in weights:
            weights["Soft & Curved"] *= 1.4
        if "Hourglass & Slender" in weights:
            weights["Hourglass & Slender"] *= 1.3
        if "Slender & Lanky" in weights:
            weights["Slender & Lanky"] *= 1.3

    # 5. Deterministic roulette roll
    total_weight = sum(weights.values())
    if total_weight <= 0:
        return candidates[0] if candidates else ("Average & Proportionate" if is_male else "Soft & Curved")

    if seed is not None:
        seed_bytes = f"physique_{seed}_{gender}_{norm_stature}_{race}".encode("utf-8")
        h = hashlib.md5(seed_bytes).hexdigest()
        roll = ((int(h[:8], 16) % 100000) / 100000.0) * total_weight
    else:
        roll = random.random() * total_weight

    cumulative = 0.0
    for p, w in weights.items():
        cumulative += w
        if roll <= cumulative:
            return p
    return candidates[0]


def normalize_appearance(raw_app: Dict[str, Any] | str = None, gender: str = "", race: str = "human", scen_key: str = "fantasy", desc: Any = "", traits: List[str] = None, role: str = "", name: str = "") -> Dict[str, Any]:
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

    char_name = str(name or (app_dict.get("name") if isinstance(app_dict, dict) else "") or "").strip()
    if not char_name and desc_text:
        first_word = desc_text.split()[0].rstrip(",.!?:;") if desc_text.split() else ""
        if len(first_word) >= 3 and first_word[0].isupper() and first_word.lower() not in ("the", "this", "she", "he", "they", "an", "a"):
            char_name = first_word

    seed_str = (desc_text + "_" + str(race) + "_" + str(char_name)).encode("utf-8")
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

    # Distinct categories: Full Beastfolk vs Half-Beast vs Humans & Fantasy Humanoids
    is_half = is_half_beast_race(race)
    is_full_beast = is_beast_race(race) and not is_half

    skin_color = str(app_dict.get("skin_color") or app_dict.get("skin") or "").strip()
    skin_type = str(app_dict.get("skin_type") or app_dict.get("coat_type") or extracted_app.get("skin_type") or "").strip().lower()
    coat_color = str(app_dict.get("coat_color") or app_dict.get("fur_color") or app_dict.get("scale_color") or app_dict.get("feather_color") or app_dict.get("coat") or extracted_app.get("coat_color") or "").strip()

    if is_full_beast:
        # Full Beastfolk (Anthro): Body covered with fur/scales/feathers; no human skin tone
        if not coat_color:
            spec = get_species_key_from_race(race, desc=desc_text)
            if spec and spec in SPECIES_TEMPLATES:
                coats = SPECIES_TEMPLATES[spec].get("coats") or SPECIES_TEMPLATES[spec].get("scales")
                if coats:
                    coat_color = coats[hash_val % len(coats)]
        if not skin_type:
            spec = get_species_key_from_race(race, desc=desc_text)
            if spec:
                if is_scaly_race(race) or spec in ("reptile", "dragon", "snake"):
                    skin_type = "scaly"
                elif spec == "bird":
                    skin_type = "feathered"
                else:
                    skin_type = "furry"
            else:
                skin_type = "furry"
        skin_color = ""
    else:
        # Half-Beasts, Humans, and Humanoids: Body has human/humanoid skin; no full-body fur coat
        coat_color = ""
        if not skin_type:
            skin_type = "skin"
        if not skin_color:
            skin_color = infer_humanoid_skin_color(race=race, name=char_name, seed=str(seed_str))

    # Stature handling (with smart race dynamic roll & narrative extraction)
    seed_str = (str(desc) + "_" + str(race) + "_" + str(char_name)).encode("utf-8")
    hash_val = int(hashlib.md5(seed_str).hexdigest(), 16) if seed_str else 0

    if app_dict.get("stature"):
        stature = normalize_stature_tier(str(app_dict["stature"]))
    elif extracted_app.get("stature"):
        stature = normalize_stature_tier(str(extracted_app["stature"]))
    else:
        stature = roll_dynamic_stature(race=race, gender=raw_g, seed=seed_str)

    # Distinctive features, Outfit style & Physique
    distinctive_features = str(app_dict.get("distinctive_features") or app_dict.get("features") or app_dict.get("marks") or "").strip()
    if not distinctive_features:
        spec = get_species_key_from_race(race, desc=desc_text)
        if spec and spec in SPECIES_TEMPLATES:
            feats_key = "hybrid_features" if is_half else "beastfolk_features"
            feat_pool = SPECIES_TEMPLATES[spec].get(feats_key) or SPECIES_TEMPLATES[spec].get("beastfolk_features") or []
            if feat_pool:
                distinctive_features = feat_pool[hash_val % len(feat_pool)]

    # Full Beastfolk features must exclude color words to prevent contradiction with body coat
    if is_full_beast and distinctive_features:
        distinctive_features = sanitize_beastfolk_features(distinctive_features)

    outfit_style = str(app_dict.get("outfit_style") or app_dict.get("outfit") or app_dict.get("clothing") or "").strip()

    raw_g = (gender or (app_dict.get("gender") if isinstance(app_dict, dict) else "") or "").strip().lower()
    is_male = any(kw in raw_g for kw in ("male", "man", "boy", "lord", "he", "him", "his")) and not any(kw in raw_g for kw in ("female", "woman"))

    physique = str(app_dict.get("physique") or "").strip()
    if physique == "Muscular & Tall":
        physique = "Muscular & Powerful"
    if not physique and extracted_app.get("physique"):
        physique = str(extracted_app["physique"]).strip()
        if physique == "Muscular & Tall":
            physique = "Muscular & Powerful"

    # Enforce incompatibility invariant: tall/towering cannot be petite
    if stature in ("tall", "towering") and physique == "Petite & Soft":
        physique = ""

    if not physique:
        physique = roll_dynamic_physique(gender=raw_g, stature=stature, race=race, seed=seed_str)

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

    is_dyed_explicit = bool(app_dict.get("is_dyed"))
    natural_color = str(app_dict.get("natural_hair_color") or "").strip().lower()
    is_dyed = False

    if not h_color:
        if extracted_app.get("hair_color"):
            h_color = extracted_app["hair_color"]
            rolled_nat = infer_natural_hair_color(
                race=race, name=char_name, coat_color=coat_color, ear_tail_feature=distinctive_features, seed=str(seed_str)
            )
            if is_full_beast and coat_color:
                contrasting = is_contrasting_shade(coat_color, h_color)
                has_dye_styling = any(kw in str(h_color).lower() for kw in ("streaks", "highlights", "balayage", "tips", "frosted", "ombre", "two-tone"))
                is_dyed = is_dyed_explicit or contrasting or has_dye_styling
            else:
                unnatural = is_unnatural_hair_color(h_color)
                is_dyed = is_dyed_explicit or unnatural
            if not natural_color or natural_color in ("unknown", "natural"):
                natural_color = rolled_nat
        else:
            # 35% hair dye rate across all archetypes (Humans, Beastfolk, Half-Beasts, Fantasy Humanoids)
            h_color, is_dyed, rolled_nat = roll_hair_color_and_dye(
                race=race,
                name=char_name,
                coat_color=coat_color,
                ear_tail_feature=distinctive_features,
                seed=str(seed_str),
                force_dye=is_dyed_explicit
            )
            if not natural_color or natural_color in ("unknown", "natural"):
                natural_color = rolled_nat
    else:
        # Explicit hair_color provided by caller or LLM
        rolled_nat = infer_natural_hair_color(
            race=race, name=char_name, coat_color=coat_color, ear_tail_feature=distinctive_features, seed=str(seed_str)
        )
        if is_full_beast and coat_color:
            contrasting = is_contrasting_shade(coat_color, h_color)
            has_dye_styling = any(kw in str(h_color).lower() for kw in ("streaks", "highlights", "balayage", "tips", "frosted", "ombre", "two-tone"))
            is_dyed = is_dyed_explicit or contrasting or has_dye_styling
        else:
            unnatural = is_unnatural_hair_color(h_color)
            is_dyed = is_dyed_explicit or unnatural
        if not natural_color or natural_color in ("unknown", "natural"):
            natural_color = rolled_nat

    # Invariant: hair cannot be dyed if it is identical to their biological natural color and lacks dye styling
    has_dye_styling = any(kw in str(h_color).lower() for kw in ("streaks", "highlights", "balayage", "tips", "frosted", "ombre", "two-tone"))
    if is_dyed and natural_color and h_color.lower() == natural_color.lower() and not has_dye_styling:
        is_dyed = False

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

    if is_dyed:
        result["is_dyed"] = True
        result["natural_hair_color"] = natural_color
    else:
        result["is_dyed"] = False
        if app_dict.get("natural_hair_color"):
            result["natural_hair_color"] = natural_color

    # Scenario-gated NSFW body attributes
    has_explicit_intimate = any(
        app_dict.get(k) for k in (
            "breast_size", "penis_size", "asset_texture", "turn_ons", "sensitive_spots",
            "fetishes", "intimate_demeanor", "intimate_dynamic",
            "act_likes", "act_dislikes", "undergarments", "bra", "underwear",
            "predetermined_intercourse", "intercourse_experience", "intimate_revealed",
            "turn_offs", "desires_and_kinks", "turn_offs_revealed"
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
                elif any(w in physique_lower for w in ("voluptuous", "curvy", "busty", "full-figured", "stacked", "hourglass", "thick", "overweight")):
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

        # Strict gender separation for anatomy
        if is_male:
            result.pop("breast_size", None)
        else:
            result.pop("penis_size", None)

        # Resolve tactile asset texture with coherence guardrail
        curr_tier = classify_asset_size_tier(result.get("penis_size" if is_male else "breast_size", ""), "male" if is_male else "female")
        incompat_set = TIER_INCOMPATIBLE_TEXTURES.get(curr_tier, set())

        tex_val = app_dict.get("asset_texture")
        if not tex_val or str(tex_val).lower() in ("none", "unknown", ""):
            tex_val = extract_asset_texture(result.get("penis_size" if is_male else "breast_size", ""), "male" if is_male else "female")

        # Anatomy & Gender Incompatibility guard: ensure texture matches character anatomy
        is_gender_incompatible = False
        if tex_val:
            if is_male:
                if tex_val in FEMALE_ASSET_TEXTURE_TEMPLATES or any(w in str(tex_val).lower() for w in ("teardrop", "perky", "bouncy", "chest fur", "underbelly down", "buoyant", "plumage")):
                    is_gender_incompatible = True
            else:
                if tex_val in MALE_ASSET_TEXTURE_TEMPLATES or any(w in str(tex_val).lower() for w in ("veined", "pulsing", "formidable", "ringed base")):
                    is_gender_incompatible = True

        # Incompatibility guard: if tex_val contradicts size tier or anatomy gender, re-roll a compatible texture
        if not tex_val or str(tex_val).lower() in ("none", "unknown", "") or any(inc.lower() in str(tex_val).lower() for inc in incompat_set) or is_gender_incompatible:
            tex_val = roll_dynamic_asset_texture(
                hash_val,
                gender="male" if is_male else "female",
                race=race,
                physique=physique,
                demeanor=result.get("intimate_demeanor", ""),
                size_tier=curr_tier,
            )
        if tex_val:
            result["asset_texture"] = str(tex_val).strip()
            # Seamlessly fuse the texture into the primary display size description
            if is_male and result.get("penis_size"):
                result["penis_size"] = fuse_asset_size_and_texture(result["penis_size"], result["asset_texture"], gender="male")
            elif not is_male and result.get("breast_size"):
                result["breast_size"] = fuse_asset_size_and_texture(result["breast_size"], result["asset_texture"], gender="female")

        # Dynamic procedural generator for fallback with dynamic synergy
        dyn_intimate = generate_dynamic_intimate_attributes(hash_val, race=race, gender=gender, dynamic=result["intimate_dynamic"], openness=result["erotic_openness"])

        # 3-Track Experience: Intercourse, Oral, Manual
        mems = app_dict.get("intimate_memories") or []

        # Analyze intimate memories for milestone evidence
        has_oral_give = False
        has_oral_rec = False
        has_manual_give = False
        has_manual_rec = False
        has_anal_give = False
        has_anal_rec = False
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
            if any(k in m_l for k in ANAL_GIVE_MEMORY_KEYWORDS):
                has_anal_give = True
            if any(k in m_l for k in ANAL_RECEIVE_MEMORY_KEYWORDS):
                has_anal_rec = True
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

        # 5. Determine Active Anal State
        anal_input = str(app_dict.get("anal_experience") or app_dict.get("anal") or "").strip().lower()
        if pred_intercourse == "virgin":
            if mems:
                if has_anal_give and has_anal_rec:
                    anal_val = "has_done_and_received_anal"
                elif has_anal_give:
                    anal_val = "has_done_anal"
                elif has_anal_rec:
                    anal_val = "has_received_anal"
                elif anal_input in ANAL_INTIMACY_STATES and anal_input not in ("inexperienced", "unknown"):
                    anal_val = anal_input
                else:
                    anal_val = anal_input if anal_input == "inexperienced" else dyn_intimate.get("anal", "inexperienced")
            elif anal_input in ANAL_INTIMACY_STATES and anal_input not in ("unknown",):
                anal_val = anal_input
            else:
                anal_val = dyn_intimate.get("anal", "inexperienced")
        elif anal_input in ANAL_INTIMACY_STATES and anal_input != "unknown":
            anal_val = anal_input
        elif pred_intercourse == "non_virgin":
            anal_val = dyn_intimate.get("anal", "inexperienced")
        else:
            anal_val = dyn_intimate.get("anal", "inexperienced")

        if pred_intercourse != "virgin":
            if has_anal_give:
                anal_val = merge_anal_states(anal_val, "has_done_anal")
            if has_anal_rec:
                anal_val = merge_anal_states(anal_val, "has_received_anal")

        result["predetermined_intercourse"] = pred_intercourse
        result["intercourse_experience"] = intercourse_val
        result["oral_experience"] = oral_val
        result["manual_experience"] = manual_val
        result["anal_experience"] = anal_val

        # Turn-ons and Sensitive Spots
        custom_turns = clean_attribute_list_string(app_dict.get("turn_ons"))
        custom_spots = clean_attribute_list_string(app_dict.get("sensitive_spots") or app_dict.get("erogenous_zones"))

        if custom_turns and custom_turns.lower() == "none" and custom_spots and custom_spots.lower() == "none":
            result["turn_ons"] = ""
            result["sensitive_spots"] = ""
        elif is_valid_persona_attribute_string(custom_spots) or is_valid_persona_attribute_string(custom_turns):
            raw_s = custom_spots if is_valid_persona_attribute_string(custom_spots) else ""
            raw_t = custom_turns if is_valid_persona_attribute_string(custom_turns) else ""
            part_spots, part_turns = partition_sensitivities_and_turn_ons(raw_s, raw_t, race=race)

            if not part_spots and not (custom_spots and custom_spots.lower() == "none"):
                part_spots = dyn_intimate.get("sensitive_spots") or ""
            if not part_turns and not (custom_turns and custom_turns.lower() == "none"):
                part_turns = dyn_intimate.get("turn_ons") or ""

            result["sensitive_spots"] = sanitize_sensitive_spots_for_species(part_spots, race=race, distinctive_features=result.get("distinctive_features", ""))
            result["turn_ons"] = sanitize_sensitive_spots_for_species(part_turns, race=race, distinctive_features=result.get("distinctive_features", ""))
        else:
            result["sensitive_spots"] = "" if (custom_spots and custom_spots.lower() == "none") else (dyn_intimate.get("sensitive_spots") or "")
            result["turn_ons"] = "" if (custom_turns and custom_turns.lower() == "none") else (dyn_intimate.get("turn_ons") or "")

        # Fetishes & Kinks: store full cleaned value (no truncation after first comma)
        custom_fetishes = clean_attribute_list_string(app_dict.get("fetishes"))
        if is_valid_persona_attribute_string(custom_fetishes):
            result["fetishes"] = custom_fetishes
        elif custom_fetishes and custom_fetishes.lower() in ("none", "none (vanilla)"):
            result["fetishes"] = "None (Vanilla)"
        else:
            result["fetishes"] = dyn_intimate["fetishes"]

        # Turn-offs (Aversions / Mood-killers)
        custom_offs = clean_attribute_list_string(app_dict.get("turn_offs") or app_dict.get("dislikes_intimate") or app_dict.get("aversions"))
        if is_valid_persona_attribute_string(custom_offs):
            result["turn_offs"] = custom_offs
        elif custom_offs and custom_offs.lower() == "none":
            result["turn_offs"] = ""
        else:
            result["turn_offs"] = dyn_intimate.get("turn_offs", "")

        # Desires & Kinks alias (ensuring active kinks fold cleanly into desires)
        result["desires_and_kinks"] = result["turn_ons"]
        if result.get("fetishes") and result["fetishes"].lower() not in ("none", "none (vanilla)", "unknown", ""):
            if result["fetishes"].lower() not in result["turn_ons"].lower():
                combined = f"{result['turn_ons']}, {result['fetishes']}".strip(", ")
                result["turn_ons"] = combined
                result["desires_and_kinks"] = combined

        # Act & Position Preferences: Likes & Dislikes
        custom_likes = clean_attribute_list_string(app_dict.get("act_likes") or app_dict.get("preferred_acts"))
        custom_dislikes = clean_attribute_list_string(app_dict.get("act_dislikes") or app_dict.get("disliked_acts"))

        legacy_kink_kws = ("mirror", "public thrill", "pinned down", "dirty talk", "restraint")
        migrated_kinks = []
        if custom_likes:
            filtered_likes = []
            for item in [x.strip() for x in custom_likes.split(",") if x.strip()]:
                if any(kw in item.lower() for kw in legacy_kink_kws):
                    migrated_kinks.append(item)
                else:
                    filtered_likes.append(item)
            custom_likes = ", ".join(filtered_likes)

        if migrated_kinks:
            curr_desires = result.get("desires_and_kinks") or result.get("turn_ons") or ""
            if not curr_desires:
                result["desires_and_kinks"] = ", ".join(migrated_kinks)
                result["turn_ons"] = result["desires_and_kinks"]
            else:
                for mk in migrated_kinks:
                    if mk.lower() not in curr_desires.lower():
                        curr_desires = f"{curr_desires}, {mk}".strip(", ")
                result["desires_and_kinks"] = curr_desires
                result["turn_ons"] = curr_desires

        result["act_likes"] = custom_likes if is_valid_persona_attribute_string(custom_likes) else dyn_intimate["act_likes"]
        result["act_dislikes"] = custom_dislikes if is_valid_persona_attribute_string(custom_dislikes) else dyn_intimate["act_dislikes"]

        # Undergarments (Bra & Underwear)
        def _clean_under_color(text: Any) -> str:
            if not text:
                return ""
            return re.sub(r'\bNude\s*/\s*Beige\b', 'Beige / Skin-Tone', str(text), flags=re.I)

        custom_under = app_dict.get("undergarments")
        if isinstance(custom_under, dict) and (custom_under.get("bra") or custom_under.get("underwear")):
            result["undergarments"] = {
                "bra": _clean_under_color(custom_under.get("bra", "")).strip(),
                "underwear": _clean_under_color(custom_under.get("underwear", "")).strip()
            }
        elif isinstance(custom_under, str) and custom_under.strip() and custom_under.lower() not in ("unknown", "n/a", "none"):
            cleaned_cu = _clean_under_color(custom_under.strip())
            if is_male:
                result["undergarments"] = {"bra": "", "underwear": cleaned_cu}
            else:
                result["undergarments"] = {"bra": cleaned_cu, "underwear": f"Matching {cleaned_cu}"}
        elif app_dict.get("bra") or app_dict.get("underwear"):
            result["undergarments"] = {
                "bra": _clean_under_color(app_dict.get("bra", "")).strip(),
                "underwear": _clean_under_color(app_dict.get("underwear", "")).strip()
            }
        else:
            dyn_under = dyn_intimate.get("undergarments", {})
            if isinstance(dyn_under, dict):
                result["undergarments"] = {
                    "bra": _clean_under_color(dyn_under.get("bra", "")),
                    "underwear": _clean_under_color(dyn_under.get("underwear", ""))
                }
            else:
                result["undergarments"] = dyn_under

    # Preserve all revealed flags and metadata state from input dictionary
    for flag_k in (
        "intimate_revealed", "intercourse_revealed", "oral_revealed", "manual_revealed",
        "demeanor_revealed", "dynamic_revealed", "openness_revealed",
        "sensitive_spots_revealed", "turn_ons_revealed", "turn_offs_revealed", "fetishes_revealed",
        "act_preferences_revealed", "mannerisms_revealed", "underwear_revealed", "all_revealed",
        "had_first_time_with_player", "intimate_memories", "past_intimate_history", "past_intimate_entries"
    ):
        if flag_k in app_dict:
            result[flag_k] = app_dict[flag_k]

    result = enforce_intimacy_safeguard_invariants(result, gender=gender)
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
        "intercourse_revealed", "oral_revealed", "manual_revealed", "anal_revealed",
        "intimate_revealed", "demeanor_revealed", "dynamic_revealed", "openness_revealed",
        "sensitive_spots_revealed", "turn_ons_revealed", "turn_offs_revealed", "fetishes_revealed",
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
    existing_anal = merged.get("anal_experience", "inexperienced")
    incoming_anal = incoming_app.get("anal_experience")

    # 3. Apply incoming data
    for k, v in incoming_app.items():
        if v is None:
            continue
        v_str = str(v).strip()
        if not v_str:
            continue

        if k in IMMUTABLE_PHYSICAL_APPEARANCE_KEYS:
            existing_val = merged.get(k)
            if existing_val is None:
                if k == "is_dyed" and merged.get("hair_color"):
                    coat = merged.get("coat_color")
                    if coat:
                        merged[k] = is_contrasting_shade(coat, merged["hair_color"])
                    else:
                        merged[k] = is_unnatural_hair_color(merged["hair_color"])
                elif k == "is_dyed":
                    merged[k] = bool(v) if not isinstance(v, str) else v.strip().lower() == "true"
                else:
                    merged[k] = v
            elif isinstance(existing_val, bool) or str(existing_val).strip().lower() in ("true", "false"):
                # Booleans like is_dyed are already established once True or False; never overwrite
                pass
            else:
                existing_str = str(existing_val).strip().lower()
                if existing_str in ("", "unknown", "none", "n/a", "null"):
                    merged[k] = v
        elif k in (
            "intimate_demeanor", "demeanor",
            "intimate_dynamic", "dynamic",
            "erotic_openness", "openness",
            "turn_ons", "sensitive_spots", "erogenous_zones",
            "turn_offs", "aversions", "dislikes_intimate", "desires_and_kinks",
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
        elif k in ("predetermined_intercourse", "intercourse_experience", "oral_experience", "manual_experience", "anal_experience"):
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
    has_anal_give = any(any(k in str(m).lower() for k in ANAL_GIVE_MEMORY_KEYWORDS) for m in mems)
    has_anal_rec = any(any(k in str(m).lower() for k in ANAL_RECEIVE_MEMORY_KEYWORDS) for m in mems)
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
        merged["anal_experience"] = existing_anal if existing_anal in ANAL_INTIMACY_STATES else "inexperienced"
    else:
        # Live encounter or verified update
        if existing_pred_i == "virgin" and incoming_intercourse == "non_virgin":
            merged["had_first_time_with_player"] = True
        merged["intercourse_experience"] = merge_intercourse_states(existing_intercourse, incoming_intercourse)
        merged["oral_experience"] = merge_oral_states(existing_oral, incoming_oral)
        merged["manual_experience"] = merge_manual_states(existing_manual, incoming_manual)
        merged["anal_experience"] = merge_anal_states(existing_anal, incoming_anal, gender=merged.get("gender", ""))

    merged = enforce_intimacy_safeguard_invariants(merged, gender=merged.get("gender", ""))

    # 5. Restore one-way true flags
    for _flag in prior_trues:
        merged[_flag] = True

    return merged


from .logic import (
    infer_intimate_dynamic_from_traits, infer_erotic_openness_from_traits,
    enforce_intimacy_safeguard_invariants, merge_manual_states, merge_anal_states,
    infer_intimate_demeanor_from_traits, merge_intercourse_states,
    merge_oral_states, sanitize_sensitive_spots_for_species,
    partition_sensitivities_and_turn_ons
)
from .generation import generate_dynamic_intimate_attributes
