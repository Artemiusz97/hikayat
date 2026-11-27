from __future__ import annotations
from .constants import (
    ASSET_TEXTURE_LEGACY_MAP_FEMALE,
    ASSET_TEXTURE_LEGACY_MAP_MALE,
    FEMALE_ASSET_TEXTURES,
    FEMALE_TIER_INCOMPATIBLE_TEXTURES,
    MALE_ASSET_TEXTURES,
    MALE_TIER_INCOMPATIBLE_TEXTURES,
    SPECIES_SURFACE_PROFILES,
)
from .constants import *
import json
import hashlib
import random
import re
from typing import Dict, Any, List
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
        r"\b(miniature|dwarf|diminutive|below[\s\-_]average|short(?!\s+(?:wait|time|while|moment|distance|walk|trip|pause|break|notice|span|list|temper|hair|skirt|dress|sleeves|cropped|crop|coat|fur|breath|[a-z\-]+\s+hair)\b)|petite|compact|average[\s\-_]height|average(?!\s+(?:day|week|score|grade|price|cost|speed|range|wait|time|person|joe|amount|rate|build|frame|physique|figure)\b)|tall|towering|gigantic|statuesque)\b",
        target,
        re.IGNORECASE
    )
    if m_stat:
        extracted["stature"] = normalize_stature_tier(m_stat.group(1))

    # 2b. Physique
    m_phys = re.search(
        r"\b(full[\s\-_]+figured|barrel[\s\-_]+chested|plus[\s\-_]+size|soft\s+curves|broad[\s\-_]+shoulders|average[\s\-_]+(?:build|frame|physique|figure)|voluptuous|curvy|hourglass|muscular|ripped|brawny|athletic|toned|stocky|burly|chubby|plump|overweight|(?:slender|slim)(?!\s+(?:tail|ears?|horns?|wings?|fingers?|wrists?|ankles?|neck|blade|sword|wand|dagger|staff|chance|margin|lead)\b)|lithe|lanky|petite|dainty)\b",
        target,
        re.IGNORECASE
    )
    if m_phys:
        norm_phys = normalize_physique(m_phys.group(1))
        if norm_phys:
            extracted["physique"] = norm_phys

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


def get_species_surface_profile(race: str = "", skin_type: str = "") -> Dict[str, str]:
    """Derives the automatic biological surface profile (skin/coat/scale/plumage/heat) from race and skin_type."""
    r = str(race or "").strip().lower()
    st = str(skin_type or "").strip().lower()

    if r in ("kitsune:myobu_fox", "ghoul:canid"):
        return dict(SPECIES_SURFACE_PROFILES["natural"])
    if r == "ghoul:humanoid":
        return dict(SPECIES_SURFACE_PROFILES["porcelain_silky"])
    if "half" in r or "hybrid" in r:
        return dict(SPECIES_SURFACE_PROFILES["natural"])
    if any(k in r for k in ("cyborg", "android", "synth")) or st == "synthetic":
        return dict(SPECIES_SURFACE_PROFILES["bio_synthetic"])
    if any(k in r for k in ("angel", "elf", "dark_elf", "drow", "orang_bunian", "bunian")):
        return dict(SPECIES_SURFACE_PROFILES["porcelain_silky"])
    if any(k in r for k in ("demon", "tiefling", "oni", "succubus", "incubus")):
        return dict(SPECIES_SURFACE_PROFILES["fever_warm"])
    if any(k in r for k in ("dragon", "dragonkin", "reptile", "snake", "lizard", "serpentine", "scaly")) or st == "scaly":
        return dict(SPECIES_SURFACE_PROFILES["scaled"])
    if any(k in r for k in ("avian", "bird", "harpy", "feathered")) or st == "feathered":
        return dict(SPECIES_SURFACE_PROFILES["feathered"])
    if any(k in r for k in ("aquatic", "merfolk", "siren", "fish")):
        return dict(SPECIES_SURFACE_PROFILES["aquatic"])
    if st != "skin" and (
        any(
            k in r
            for k in (
                "beastfolk", "fox", "cat", "neko", "kitsune", "wolf", "rabbit", "bunny",
                "tiger", "lion", "bear", "mouse", "rat", "hamster", "squirrel",
                "hedgehog", "ferret", "weasel", "fennec", "cheetah", "minotaur", "boar", "bovine",
            )
        )
        or st == "furry"
    ):
        return dict(SPECIES_SURFACE_PROFILES["furred"])
    return dict(SPECIES_SURFACE_PROFILES["natural"])


def normalize_asset_texture(texture_str: Any, gender: str = "female", size_tier: str = "") -> str:
    """Normalizes canonical, legacy 'X & Y', and synonym asset texture strings to canonical single-word labels."""
    if not texture_str or not isinstance(texture_str, str):
        return ""
    s_clean = re.sub(r"\s+", " ", texture_str.strip())
    s_low = s_clean.lower()
    if s_low in ("", "unknown", "none", "null", "n/a", "auto", "__auto__"):
        return ""

    is_male = any(kw in str(gender).lower() for kw in ("male", "man", "boy")) and "female" not in str(gender).lower()
    canonical_list = MALE_ASSET_TEXTURES if is_male else FEMALE_ASSET_TEXTURES
    canonical_lower = {item.lower(): item for item in canonical_list}
    legacy_map = ASSET_TEXTURE_LEGACY_MAP_MALE if is_male else ASSET_TEXTURE_LEGACY_MAP_FEMALE

    if s_low in canonical_lower:
        return canonical_lower[s_low]
    if s_low in legacy_map:
        return legacy_map[s_low]

    if is_male:
        if any(k in s_low for k in ("veined", "throbbing")):
            return "Veined"
        if any(k in s_low for k in ("curved", "angled")):
            return "Curved"
        if any(k in s_low for k in ("tapered", "slender")):
            return "Tapered"
        if "heavy" in s_low:
            return "Heavy"
        if any(k in s_low for k in ("thick", "dense", "formidable", "sturdy", "girthy")):
            return "Thick"
        if any(k in s_low for k in ("firm", "toned", "compact", "athletic", "resilient")):
            return "Firm"
        if any(k in s_low for k in ("sensitive", "responsive", "pulsing", "trembling")):
            return "Sensitive"
        if any(k in s_low for k in ("smooth", "silky", "glistening", "velvety", "supple", "soft", "warm", "fur", "scale", "feather", "plumage")):
            return "Smooth"
    else:
        if any(k in s_low for k in ("perky", "high-set", "high set", "buoyant")):
            return "Perky"
        if any(k in s_low for k in ("pillowy", "yielding")):
            return "Pillowy"
        if "plush" in s_low or "heavy" in s_low:
            return "Plush"
        if "bouncy" in s_low:
            return "Bouncy"
        if "teardrop" in s_low:
            return "Teardrop"
        if any(k in s_low for k in ("delicate", "tender")):
            return "Delicate"
        if any(k in s_low for k in ("firm", "toned", "compact", "athletic", "resilient", "dense")):
            return "Firm"
        if any(k in s_low for k in ("sensitive", "responsive", "pulsing", "trembling")):
            return "Sensitive"
        if any(k in s_low for k in ("smooth", "silky", "glistening", "velvety", "supple", "soft", "warm", "fur", "scale", "feather", "plumage")):
            tier_low = str(size_tier or "").strip().lower()
            if "soft" in s_low and tier_low in ("flat", "small") and not any(w in s_low for w in ("smooth", "supple", "fur", "scale", "feather")):
                return "Delicate"
            return "Supple"
    return ""


def heal_asset_texture_for_context(texture: Any, gender: str = "female", size_tier: str = "average") -> str:
    """Heals a normalized asset texture when it contradicts the character's size tier."""
    tier = str(size_tier or "average").strip().lower()
    norm = normalize_asset_texture(texture, gender=gender, size_tier=tier)
    if not norm:
        return ""

    is_male = any(kw in str(gender).lower() for kw in ("male", "man", "boy")) and "female" not in str(gender).lower()
    if is_male:
        if tier in ("flat", "small"):
            if norm == "Heavy":
                return "Firm"
            if norm == "Thick":
                return "Smooth"
        elif tier == "huge" and norm == "Tapered":
            return "Thick"
        return norm

    if tier == "flat":
        if norm in ("Plush", "Pillowy", "Teardrop"):
            return "Supple"
        if norm == "Bouncy":
            return "Perky"
    elif tier == "small":
        if norm in ("Plush", "Pillowy"):
            return "Supple"
        if norm == "Bouncy":
            return "Perky"
    elif tier in ("large", "huge") and norm == "Delicate":
        return "Supple"
    return norm


def strip_asset_texture_from_size(size_str: str, gender: str = "female") -> str:
    """Strips stacked canonical or legacy texture prefixes and parentheticals from a size string."""
    s = str(size_str or "").strip()
    if not s:
        return ""
    s = re.sub(r"^\((.*?)\)$", r"\1", s).strip()

    # Strip trailing parenthetical if it contains a recognized texture
    paren_m = re.search(r"\s*\(([^()]+)\)\s*$", s)
    if paren_m and normalize_asset_texture(paren_m.group(1), gender=gender):
        s = s[:paren_m.start()].strip()

    is_male = any(kw in str(gender).lower() for kw in ("male", "man", "boy")) and "female" not in str(gender).lower()
    legacy_keys = sorted(
        list((ASSET_TEXTURE_LEGACY_MAP_MALE if is_male else ASSET_TEXTURE_LEGACY_MAP_FEMALE).keys()),
        key=len,
        reverse=True,
    )
    canonical_tokens = {t.lower() for t in (MALE_ASSET_TEXTURES if is_male else FEMALE_ASSET_TEXTURES)}

    changed = True
    while changed and s:
        changed = False
        s_low = s.lower()
        for leg in legacy_keys:
            if s_low == leg:
                return ""
            if s_low.startswith(leg + " "):
                s = s[len(leg):].strip(" ,-")
                changed = True
                break
        if changed:
            continue
        parts = s.split(None, 1)
        if len(parts) == 2 and parts[0].strip(",-").lower() in canonical_tokens:
            s = parts[1].strip()
            changed = True

    return s


def extract_asset_texture(size_str: str, gender: str = "female") -> str:
    """Extracts a canonical single-word tactile/shape trait from a compound size string."""
    if not size_str or not isinstance(size_str, str):
        return ""
    is_male = any(kw in str(gender).lower() for kw in ("male", "man", "boy")) and "female" not in str(gender).lower()
    tier = classify_asset_size_tier(size_str, gender="male" if is_male else "female")
    direct = normalize_asset_texture(size_str, gender="male" if is_male else "female", size_tier=tier)
    if direct:
        return direct
    return ""


def fuse_asset_size_and_texture(size_str: str, texture_str: str, gender: str = "female") -> str:
    """Combines a size string and canonical tactile texture into a clean phrase without stacking or brackets."""
    s = str(size_str or "").strip()
    t = str(texture_str or "").strip()
    norm_t = normalize_asset_texture(t, gender=gender) or re.sub(r"^\((.*?)\)$", r"\1", t).strip()
    if not s and not norm_t:
        return ""
    if not norm_t:
        return s
    if not s:
        return norm_t

    is_male = any(kw in str(gender).lower() for kw in ("male", "man", "boy")) and "female" not in str(gender).lower()
    s_stripped = strip_asset_texture_from_size(s, gender="male" if is_male else "female") or s
    s_stripped = re.sub(r"^\((.*?)\)$", r"\1", s_stripped).strip()
    s_low = s_stripped.lower().strip()

    bare_female_tiers = {
        "flat": "AA-Cup",
        "small": "B-Cup",
        "average": "C-Cup",
        "large": "D-Cup",
        "huge": "E-Cup",
    }
    bare_male_tiers = {
        "flat": "Tiny",
        "small": "Compact",
        "average": "Average",
        "large": "Large",
        "huge": "Huge",
    }
    if not is_male and s_low in bare_female_tiers:
        return f"{norm_t} {bare_female_tiers[s_low]}"
    if is_male and s_low in bare_male_tiers:
        return f"{norm_t} {bare_male_tiers[s_low]}"

    if not is_male:
        cup_match = re.search(r"\b([A-Ha-h]+(?:\+)?-Cup)\b", s_stripped, re.IGNORECASE)
        if cup_match:
            cup_part = cup_match.group(1).upper()
            if cup_part.endswith("-CUP"):
                cup_part = cup_part[:-4] + "-Cup"
            return f"{norm_t} {cup_part}"

        if any(w in s_low for w in ("flat", "barely")):
            if "flat" not in norm_t.lower():
                return f"{norm_t} Flat Chest"
            return norm_t

        redundant_prefixes = {
            "generous", "voluptuous", "modest", "petite", "heavy", "bountiful",
            "shapely", "toned", "firm", "soft", "full", "small", "large", "average",
        }
        words = s_stripped.split()
        filtered_words = [w for w in words if w.lower() not in redundant_prefixes]
        base_remainder = " ".join(filtered_words).strip()
        if base_remainder:
            return f"{norm_t} {base_remainder}"
        return f"{norm_t} {s_stripped}"
    else:
        inch_match = re.search(r'(\d+(?:\.\d+)?\s*(?:"|inch(?:es)?))', s_stripped, re.IGNORECASE)
        if inch_match:
            inch_part = inch_match.group(1).strip()
            if "inch" in inch_part.lower():
                val = re.findall(r"\d+(?:\.\d+)?", inch_part)[0]
                inch_part = f'{val}"'
            return f"{norm_t} {inch_part}"

        redundant_prefixes = {
            "thick", "long", "massive", "compact", "slender", "sturdy",
            "dense", "toned", "formidable", "large", "huge", "small",
        }
        words = s_stripped.split()
        filtered_words = [w for w in words if w.lower() not in redundant_prefixes]
        base_remainder = " ".join(filtered_words).strip()
        if base_remainder:
            return f"{norm_t} {base_remainder}"
        return f"{norm_t} {s_stripped}"


def roll_dynamic_asset_texture(
    seed_val: Any = 0,
    gender: str = "female",
    race: str = "human",
    physique: str = "",
    demeanor: str = "",
    size_tier: str = "average",
    seed: Any = None,
) -> str:
    """Rolls a canonical single-word tactile texture with size-, physique-, and race-aware weights."""
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
    pool = list(MALE_ASSET_TEXTURES if is_male else FEMALE_ASSET_TEXTURES)

    tier_low = str(size_tier or "average").strip().lower()
    incompat_map = MALE_TIER_INCOMPATIBLE_TEXTURES if is_male else FEMALE_TIER_INCOMPATIBLE_TEXTURES
    incompat = incompat_map.get(tier_low, set())
    candidate_pool = [t for t in pool if t not in incompat] or pool

    weights: Dict[str, float] = {item: 1.0 for item in candidate_pool}

    # 1. Size tier modulation
    if is_male:
        if tier_low in ("flat", "small"):
            for k, m in (("Firm", 1.4), ("Smooth", 1.5), ("Sensitive", 1.5), ("Tapered", 1.4)):
                if k in weights:
                    weights[k] *= m
        elif tier_low in ("large", "huge"):
            for k, m in (("Thick", 1.6), ("Heavy", 1.5), ("Veined", 1.5), ("Curved", 1.3)):
                if k in weights:
                    weights[k] *= m
            if tier_low == "large" and "Tapered" in weights:
                weights["Tapered"] *= 0.5
    else:
        if tier_low in ("flat", "small"):
            for k, m in (("Perky", 1.6), ("Delicate", 1.5), ("Firm", 1.3), ("Sensitive", 1.3)):
                if k in weights:
                    weights[k] *= m
        elif tier_low in ("large", "huge"):
            for k, m in (("Pillowy", 1.6), ("Plush", 1.6), ("Bouncy", 1.5), ("Teardrop", 1.3)):
                if k in weights:
                    weights[k] *= m
            if "Perky" in weights:
                weights["Perky"] *= 0.35 if tier_low == "huge" else 0.6

    # 2. Physique modulation (aligned with canonical 9-tier physique)
    p_low = str(physique or "").strip().lower()
    if any(k in p_low for k in ("athletic", "muscular", "toned", "fit")):
        for k, m in (("Firm", 1.6), ("Perky", 1.3), ("Veined", 1.5)):
            if k in weights:
                weights[k] *= m
    elif any(k in p_low for k in ("voluptuous", "chubby", "overweight", "plump")):
        for k, m in (("Pillowy", 1.6), ("Plush", 1.6), ("Bouncy", 1.3), ("Heavy", 1.5), ("Thick", 1.5)):
            if k in weights:
                weights[k] *= m
    elif any(k in p_low for k in ("slim", "petite", "slender", "thin", "lean")):
        for k, m in (("Delicate", 1.5), ("Perky", 1.4), ("Sensitive", 1.3), ("Tapered", 1.4), ("Smooth", 1.3)):
            if k in weights:
                weights[k] *= m
    elif "curvy" in p_low:
        for k, m in (("Supple", 1.4), ("Teardrop", 1.4), ("Plush", 1.3), ("Bouncy", 1.3)):
            if k in weights:
                weights[k] *= m
    elif "stocky" in p_low:
        for k, m in (("Firm", 1.3), ("Plush", 1.3), ("Thick", 1.5), ("Heavy", 1.4)):
            if k in weights:
                weights[k] *= m

    # 3. Race / Species archetype soft weights (zero species leakage into strings)
    r_low = str(race or "").strip().lower()
    surface_key = get_species_surface_profile(race=r_low).get("key", "natural")
    is_small_beast = any(
        k in r_low for k in ("cat", "neko", "fox", "kitsune", "fennec", "rabbit", "bunny", "mouse", "rat", "hamster", "squirrel", "ferret", "weasel")
    )
    is_large_race = not is_small_beast and (
        any(k in r_low for k in ("wolf", "tiger", "lion", "bear", "dragon", "orc", "minotaur", "rhino", "elephant", "boar", "bovine", "dwarf"))
        or bool(re.search(r"\box(en)?\b", r_low))
    )

    if surface_key == "porcelain_silky" or is_small_beast:
        for k, m in (("Perky", 1.25), ("Supple", 1.25), ("Delicate", 1.25), ("Sensitive", 1.25), ("Smooth", 1.25), ("Tapered", 1.25)):
            if k in weights:
                weights[k] *= m
    elif surface_key == "scaled" or is_large_race:
        for k, m in (("Firm", 1.3), ("Plush", 1.2), ("Thick", 1.35), ("Heavy", 1.3), ("Veined", 1.25)):
            if k in weights:
                weights[k] *= m
    elif surface_key == "fever_warm":
        for k, m in (("Sensitive", 1.3), ("Supple", 1.2), ("Plush", 1.2), ("Veined", 1.25), ("Curved", 1.25), ("Heavy", 1.2)):
            if k in weights:
                weights[k] *= m
    elif surface_key == "bio_synthetic":
        for k, m in (("Firm", 1.35), ("Perky", 1.3), ("Smooth", 1.3), ("Supple", 1.2)):
            if k in weights:
                weights[k] *= m
    elif surface_key == "aquatic":
        for k, m in (("Supple", 1.3), ("Smooth", 1.35), ("Sensitive", 1.2), ("Curved", 1.2)):
            if k in weights:
                weights[k] *= m
    elif surface_key == "feathered":
        for k, m in (("Perky", 1.3), ("Delicate", 1.3), ("Supple", 1.2), ("Smooth", 1.2), ("Tapered", 1.25)):
            if k in weights:
                weights[k] *= m
    elif surface_key == "furred":
        for k, m in (("Supple", 1.25), ("Plush", 1.25), ("Sensitive", 1.2), ("Smooth", 1.2)):
            if k in weights:
                weights[k] *= m

    total_weight = sum(weights.values())
    if total_weight <= 0:
        return candidate_pool[0]

    roll = (((abs(effective_seed) * 2654435761) % 10000) / 10000.0) * total_weight
    cumulative = 0.0
    for item in candidate_pool:
        cumulative += weights.get(item, 1.0)
        if roll <= cumulative:
            return item
    return candidate_pool[-1]
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
    - Miniature races (dwarf, gnome, halfling, goblin, kobold, pixie, fairy): 100% miniature for all genders.
    - Non-binary / custom genders use the M/F midpoint distribution of their species bracket.
    - Male Standard Races & Medium Beastfolk (Default): 5% short, 15% below_avg, 50% avg, 25% tall, 5% towering.
    - Female Standard Races & Medium Beastfolk (Default): 10% short, 34% below_avg, 45% avg, 10% tall, 1% towering.
    - Tall / Graceful Races (elf, high_elf, dark_elf, drow, angel, orang_bunian):
      * Male: 2% short, 8% below_avg, 40% avg, 38% tall, 12% towering.
      * Female: 4% short, 16% below_avg, 45% avg, 28% tall, 7% towering.
    - Male Large Beastfolk & Large Humanoids (orc, oni, giant, troll, ogre, etc.): 1/4/25/45/25.
    - Female Large Beastfolk & Large Humanoids: 1/14/55/20/10.
    - Male Small Agile Beastfolk: 10% short, 30% below_avg, 43% avg, 15% tall, 2% towering.
    - Female Small Agile Beastfolk: 15% short, 45% below_avg, 34% avg, 5% tall, 1% towering.
    - Male Tiny Beastfolk: 34% short, 45% below_avg, 15% avg, 5% tall, 1% towering.
    - Female Tiny Beastfolk: 55% short, 35% below_avg, 7% avg, 2% tall, 1% towering.
    """
    r = (race_str or "human").strip().lower()
    g = (gender or "").strip().lower()
    is_male = is_male_gender(g)
    is_fem = is_female_gender(g)
    is_nonbinary = bool(g) and not is_male and not is_fem

    def _pick_gender_table(male_tbl: Dict[str, float], fem_tbl: Dict[str, float]) -> Dict[str, float]:
        if is_nonbinary:
            return {
                tier: round((float(male_tbl.get(tier, 0.0)) + float(fem_tbl.get(tier, 0.0))) / 2.0, 6)
                for tier in STATURE_TIERS
            }
        return dict(fem_tbl if is_fem else male_tbl)

    # 1. Miniature Fantasy Species (strictly miniature for all genders)
    if any(k in r for k in ("dwarf", "gnome", "halfling", "goblin", "kobold", "pixie", "fairy")):
        return dict(STATURE_WEIGHTS_MINIATURE)

    # 2. Hybrids / Half-Beast default to Standard
    if "half" in r or "hybrid" in r:
        return _pick_gender_table(STATURE_WEIGHTS_MALE_STANDARD, STATURE_WEIGHTS_FEMALE_STANDARD)

    # 3. Tiny/Smallest Beastfolk (rabbit, mouse, etc.)
    if any(k in r for k in ("rabbit", "bunny", "mouse", "rat", "hamster", "squirrel", "hedgehog")):
        return _pick_gender_table(STATURE_WEIGHTS_MALE_TINY_BEASTFOLK, STATURE_WEIGHTS_FEMALE_TINY_BEASTFOLK)

    # 4. Small Agile Beastfolk (cat, fox, fennec, etc.)
    if any(k in r for k in ("cat", "neko", "fox", "kitsune", "fennec", "ferret", "weasel")):
        return _pick_gender_table(STATURE_WEIGHTS_MALE_SMALL_BEASTFOLK, STATURE_WEIGHTS_FEMALE_SMALL_BEASTFOLK)

    # 5. Cheetah and similarly sized medium species (same as standard race)
    if "cheetah" in r:
        return _pick_gender_table(STATURE_WEIGHTS_MALE_STANDARD, STATURE_WEIGHTS_FEMALE_STANDARD)

    # 6. Large Beastfolk & Large Humanoids (wolf, tiger, lion, bear, dragon, orc, oni, giant, troll, ogre, etc.)
    large_kws = (
        "wolf", "tiger", "lion", "bear", "dragon", "orc", "minotaur", "rhino",
        "elephant", "ox", "boar", "bovine", "oni", "giant", "troll", "ogre",
    )
    if any((bool(re.search(rf"\b{k}(?:en)?\b", r)) if k in ("ox", "oni") else k in r) for k in large_kws):
        return _pick_gender_table(STATURE_WEIGHTS_MALE_LARGE_BEASTFOLK, STATURE_WEIGHTS_FEMALE_LARGE_BEASTFOLK)

    # 7. Tall / Graceful Fantasy Races (elf, high_elf, dark_elf, drow, angel, orang_bunian)
    if any(k in r for k in ("elf", "drow", "angel", "bunian")):
        return _pick_gender_table(STATURE_WEIGHTS_MALE_TALL_GRACEFUL, STATURE_WEIGHTS_FEMALE_TALL_GRACEFUL)

    # 8. Standard Races (human, demon, default)
    return _pick_gender_table(STATURE_WEIGHTS_MALE_STANDARD, STATURE_WEIGHTS_FEMALE_STANDARD)


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
    """Rolls a height-, gender-, and race-aware canonical physique tier.
    - Uses the unified 7 single-word canonical tiers (`PHYSIQUE_TIERS`).
    - Symmetric 6 vs. 6 gender options (Custom/Non-Binary uses all 7):
      * male excludes Voluptuous
      * female excludes Muscular
      * orang_bunian excludes Stocky, Chubby
    - Soft probability weights for height, gender, and race (no role/occupation weighting).
    """
    raw_g = (gender or "female").strip().lower()
    is_male = is_male_gender(raw_g)
    is_female = is_female_gender(raw_g)

    norm_stature = normalize_stature_tier(stature)
    r = (race or "").lower()

    # 1. Hard exclusions
    excluded = set(STATURE_INCOMPATIBLE_PHYSIQUES.get(norm_stature, set()))
    if is_male:
        excluded.update(GENDER_INCOMPATIBLE_PHYSIQUES.get("male", set()))
    elif is_female:
        excluded.update(GENDER_INCOMPATIBLE_PHYSIQUES.get("female", set()))
    if "bunian" in r:
        excluded.update({"Stocky", "Chubby"})

    candidates = [p for p in PHYSIQUE_TIERS if p not in excluded]
    if not candidates:
        candidates = ["Average"]

    # 2. Gender baseline weights (non-binary/custom uses balanced baseline across all 7)
    if is_male:
        base_weights = {
            "Average": 1.10,
            "Athletic": 1.00,
            "Slim": 0.85,
            "Muscular": 0.85,
            "Stocky": 0.45,
            "Chubby": 0.15,
        }
    elif is_female:
        base_weights = {
            "Slim": 1.40,
            "Average": 1.25,
            "Athletic": 1.00,
            "Voluptuous": 0.95,
            "Stocky": 0.25,
            "Chubby": 0.15,
        }
    else:
        base_weights = {
            "Average": 1.00,
            "Slim": 1.00,
            "Athletic": 0.95,
            "Muscular": 0.60,
            "Voluptuous": 0.60,
            "Stocky": 0.35,
            "Chubby": 0.15,
        }

    weights = {p: base_weights.get(p, 0.5) for p in candidates}

    # 3. Stature modifiers
    if norm_stature in ("miniature", "short", "below_average"):
        if "Slim" in weights:
            weights["Slim"] *= 1.6
        if "Stocky" in weights:
            weights["Stocky"] *= 1.3
        if "Voluptuous" in weights:
            weights["Voluptuous"] *= 1.1
    elif norm_stature in ("tall", "towering"):
        if "Slim" in weights:
            weights["Slim"] *= 1.5
        if "Athletic" in weights:
            weights["Athletic"] *= 1.4
        if "Muscular" in weights:
            weights["Muscular"] *= 1.4
        if "Voluptuous" in weights:
            weights["Voluptuous"] *= 1.2

    # 4. Race modifiers (explicitly no role/occupation bias)
    if "bunian" in r:
        for _grace, _mult in (("Slim", 2.0), ("Athletic", 1.4), ("Voluptuous", 1.1)):
            if _grace in weights:
                weights[_grace] *= _mult
    elif any(k in r for k in ("elf", "dark_elf", "drow")):
        for _grace, _mult in (("Slim", 2.0), ("Athletic", 1.4)):
            if _grace in weights:
                weights[_grace] *= _mult

    if "dwarf" in r:
        if "Stocky" in weights:
            weights["Stocky"] *= 2.8
        if "Muscular" in weights:
            weights["Muscular"] *= 1.8
        if is_female and "Athletic" in weights:
            weights["Athletic"] *= 1.4
        if "Voluptuous" in weights:
            weights["Voluptuous"] *= 1.15
        if "Slim" in weights:
            weights["Slim"] *= 0.6

    is_small_beast = any(
        k in r for k in (
            "cat", "neko", "fox", "kitsune", "fennec", "rabbit", "bunny",
            "mouse", "rat", "hamster", "squirrel", "hedgehog", "ferret", "weasel",
        )
    )
    is_large_beast = not is_small_beast and any(
        (bool(re.search(r"\box(en)?\b", r)) if k == "ox" else k in r)
        for k in ("wolf", "tiger", "lion", "bear", "dragon", "orc", "minotaur", "rhino", "elephant", "ox", "boar", "bovine")
    )

    if is_large_beast:
        if "Athletic" in weights:
            weights["Athletic"] *= 1.8 if is_female else 1.5
        if "Muscular" in weights:
            weights["Muscular"] *= 1.8
        if "Stocky" in weights:
            weights["Stocky"] *= 1.4
        if "Voluptuous" in weights:
            weights["Voluptuous"] *= 1.3
        if "Slim" in weights:
            weights["Slim"] *= 0.65
    elif is_small_beast:
        if "Slim" in weights:
            weights["Slim"] *= 2.0
        if "Voluptuous" in weights:
            weights["Voluptuous"] *= 1.1
        if "Muscular" in weights:
            weights["Muscular"] *= 0.5
        if "Stocky" in weights:
            weights["Stocky"] *= 0.5

    # 5. Deterministic roulette roll
    total_weight = sum(weights.values())
    if total_weight <= 0:
        return candidates[0] if candidates else "Average"

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


def roll_dynamic_breast_size(physique: str = "Average", hash_val: int = 0) -> str:
    """Soft-weighted cup correlation for NSFW female NPCs based on canonical physique."""
    canon = normalize_physique(physique) or "Average"
    if canon == "Slim":
        pool = [
            ("Flat AA-Cup", 10),
            ("Petite A-Cup", 18),
            ("Soft A-Cup", 18),
            ("Modest B-Cup", 20),
            ("Perky B-Cup", 20),
            ("Shapely C-Cup", 10),
            ("Voluptuous D-Cup", 4),
        ]
    elif canon in ("Athletic", "Muscular"):
        pool = [
            ("Soft A-Cup", 12),
            ("Perky B-Cup", 22),
            ("Athletic B-Cup", 22),
            ("Toned C-Cup", 18),
            ("Shapely C-Cup", 16),
            ("Full D-Cup", 10),
        ]
    elif canon == "Voluptuous":
        pool = [
            ("Full C-Cup", 12),
            ("Voluptuous D-Cup", 36),
            ("Generous DD-Cup", 30),
            ("Heavy D-Cup", 12),
            ("Bountiful E-Cup", 10),
        ]
    elif canon == "Chubby":
        pool = [
            ("Modest B-Cup", 10),
            ("Full C-Cup", 30),
            ("Heavy D-Cup", 20),
            ("Generous DD-Cup", 18),
            ("Bountiful E-Cup", 22),
        ]
    else:  # Average / Stocky
        pool = [
            ("Soft A-Cup", 10),
            ("Modest B-Cup", 35),
            ("Shapely C-Cup", 20),
            ("Full C-Cup", 18),
            ("Voluptuous D-Cup", 17),
        ]

    total = sum(w for _, w in pool)
    pick = (abs(int(hash_val or 0)) // 17) % total
    acc = 0
    for cup, w in pool:
        acc += w
        if pick < acc:
            return cup
    return pool[0][0]


def roll_dynamic_penis_size(stature: str = "average", race: str = "", hash_val: int = 0) -> str:
    """Weighted procedural fallback for NSFW male NPCs centered around Average with gentle race/stature skew."""
    norm_st = normalize_stature_tier(stature)
    r = str(race or "").lower()
    weights = {
        "Small": 15.0,
        "Average": 50.0,
        "Large": 25.0,
        "Huge": 10.0,
    }
    is_tiny = any(k in r for k in ("rabbit", "bunny", "mouse", "rat", "hamster", "squirrel", "hedgehog"))
    is_large = not is_tiny and any(
        (bool(re.search(r"\box(en)?\b", r)) if k == "ox" else k in r)
        for k in ("wolf", "tiger", "lion", "bear", "dragon", "orc", "minotaur", "rhino", "elephant", "ox", "boar", "bovine")
    )
    if is_large or norm_st in ("tall", "towering"):
        weights["Small"] *= 0.6
        weights["Large"] *= 1.35
        weights["Huge"] *= 1.5
    elif is_tiny or norm_st in ("miniature", "short"):
        weights["Small"] *= 1.4
        weights["Large"] *= 0.75
        weights["Huge"] *= 0.5

    total = sum(weights.values())
    roll = (((abs(int(hash_val or 0)) * 2654435761) % 10000) / 10000.0) * total
    acc = 0.0
    for sz, w in weights.items():
        acc += w
        if roll <= acc:
            return sz
    return "Average"


def is_feral_rear_excluded(race: str = "") -> bool:
    """Returns True for feral non-humanoid species that skip humanoid rear anatomy and SDXL rear tags."""
    r = str(race or "").strip().lower().replace("-", "_")
    return r in (
        "kitsune:myobu_fox", "kitsune_myobu_fox", "kitsune:fox", "myobu_fox",
        "ghoul:canid", "ghoul_canid", "al_ghul:canid", "ghoul:hound", "ghoul:beast",
    )


def normalize_rear_texture(texture_str: Any, size_tier: str = "") -> str:
    """Normalizes rear tactile texture strings to canonical single-word labels in REAR_ASSET_TEXTURES."""
    if not texture_str or not isinstance(texture_str, str):
        return ""
    s_clean = re.sub(r"\s+", " ", texture_str.strip())
    s_low = s_clean.lower()
    if s_low in ("", "unknown", "none", "null", "n/a", "auto", "__auto__"):
        return ""

    canonical_lower = {item.lower(): item for item in REAR_ASSET_TEXTURES}
    if s_low in canonical_lower:
        return canonical_lower[s_low]
    if s_low in REAR_TEXTURE_SYNONYMS:
        return REAR_TEXTURE_SYNONYMS[s_low]

    # Do not confuse size labels ('flat', 'compact', 'shapely', 'plump', 'bountiful') as textures unless a texture keyword appears
    for syn_k, canon_v in REAR_TEXTURE_SYNONYMS.items():
        if re.search(rf"\b{re.escape(syn_k)}\b", s_low):
            return canon_v
    for tex_l, canon_v in canonical_lower.items():
        if re.search(rf"\b{re.escape(tex_l)}\b", s_low):
            return canon_v
    return ""


def strip_rear_texture_from_size(size_str: Any) -> str:
    """Strips canonical/synonym rear texture prefixes and parentheticals, returning the bare canonical rear size label."""
    s = str(size_str or "").strip()
    if not s or s.lower() in ("none", "unknown", "null", "n/a", "auto", "__auto__"):
        return ""
    s = re.sub(r"^\((.*?)\)$", r"\1", s).strip()

    paren_m = re.search(r"\s*\(([^()]+)\)\s*$", s)
    if paren_m and normalize_rear_texture(paren_m.group(1)):
        s = s[:paren_m.start()].strip()

    size_label_tokens = {lbl.lower() for lbl in REAR_SIZE_LABELS.values()}
    tex_tokens = ({t.lower() for t in REAR_ASSET_TEXTURES} | set(REAR_TEXTURE_SYNONYMS.keys())) - size_label_tokens

    parts = [p.strip(",-") for p in s.split() if p.strip(",-")]
    remaining = [p for p in parts if p.lower() not in tex_tokens and p.lower() not in ("rear", "ass", "butt", "hips")]
    if not remaining:
        # Check if original had only a size word mixed with 'rear'
        return ""
    candidate = " ".join(remaining).strip()
    return normalize_rear_size_label(candidate) or candidate


def classify_rear_size_tier(size_str: Any) -> str:
    """Classifies a rear size string into one of 5 canonical tiers: 'flat', 'small', 'average', 'large', 'huge'."""
    if not size_str or not isinstance(size_str, str):
        return "average"
    s = str(size_str or "").strip()
    if not s or s.lower() in ("none", "unknown", "null", "n/a", "auto", "__auto__"):
        return "average"

    s = re.sub(r"^\((.*?)\)$", r"\1", s).strip()
    paren_m = re.search(r"\s*\(([^()]+)\)\s*$", s)
    if paren_m and normalize_rear_texture(paren_m.group(1)):
        s = s[:paren_m.start()].strip()

    size_label_tokens = {lbl.lower() for lbl in REAR_SIZE_LABELS.values()}
    tex_tokens = ({t.lower() for t in REAR_ASSET_TEXTURES} | set(REAR_TEXTURE_SYNONYMS.keys())) - size_label_tokens
    parts = [p.strip(",-").lower() for p in s.split() if p.strip(",-")]
    core_parts = [p for p in parts if p not in tex_tokens] or parts
    s_low = " ".join(core_parts)

    if any(w in s_low for w in ("flat", "tiny", "slight", "barely")):
        return "flat"
    if any(w in s_low for w in ("compact", "small", "modest")):
        return "small"
    if any(w in s_low for w in ("bountiful", "huge", "massive", "enormous", "gigantic", "colossal", "voluptuous")):
        return "huge"
    if any(w in s_low for w in ("plump", "large", "generous", "thick", "wide", "full", "heavy", "curvy")):
        return "large"
    if any(w in s_low for w in ("shapely", "average", "medium", "moderate", "balanced")):
        return "average"
    return "average"


def normalize_rear_size_label(raw_rear_size: Any) -> str:
    """Normalizes a rear size descriptor or tier key to its canonical label (Flat/Compact/Shapely/Plump/Bountiful)."""
    if not raw_rear_size or not isinstance(raw_rear_size, str):
        return ""
    s_low = str(raw_rear_size).strip().lower()
    if s_low in ("", "none", "unknown", "null", "n/a", "auto", "__auto__"):
        return ""
    if s_low in REAR_SIZE_LABELS:
        return REAR_SIZE_LABELS[s_low]
    # Ensure string actually expresses a size word rather than only a texture word
    size_label_tokens = {lbl.lower() for lbl in REAR_SIZE_LABELS.values()}
    tex_only = ({t.lower() for t in REAR_ASSET_TEXTURES} | set(REAR_TEXTURE_SYNONYMS.keys())) - size_label_tokens
    tokens = [p.strip("(),-").lower() for p in s_low.split() if p.strip("(),-")]
    non_tex = [t for t in tokens if t not in tex_only and t not in ("rear", "ass", "butt")]
    if not non_tex:
        return ""
    tier = classify_rear_size_tier(" ".join(non_tex))
    return REAR_SIZE_LABELS.get(tier, "Shapely")


def heal_rear_texture_for_context(texture: Any, size_tier: str = "average") -> str:
    """Heals a rear texture when incompatible with the character's rear size tier."""
    raw_t = str(size_tier or "average").strip().lower()
    tier = raw_t if raw_t in REAR_SIZE_TIERS else classify_rear_size_tier(raw_t)
    norm = normalize_rear_texture(texture, size_tier=tier)
    if not norm:
        return ""
    incompat = REAR_TIER_INCOMPATIBLE_TEXTURES.get(tier, set())
    if norm in incompat:
        if tier in ("flat", "small"):
            return "Supple"
        if tier in ("large", "huge"):
            return "Firm"
    return norm


def extract_rear_texture(raw_rear_size: Any, explicit_texture: Any = "") -> str:
    """Extracts canonical rear texture from explicit texture or fused rear size string."""
    if explicit_texture:
        direct = normalize_rear_texture(str(explicit_texture))
        if direct:
            return direct
    if not raw_rear_size or not isinstance(raw_rear_size, str):
        return ""
    s = str(raw_rear_size).strip()
    paren_m = re.search(r"\s*\(([^()]+)\)\s*$", s)
    if paren_m:
        t_paren = normalize_rear_texture(paren_m.group(1))
        if t_paren:
            return t_paren
    tokens = [p.strip(",-") for p in re.sub(r"\([^)]*\)", "", s).split() if p.strip(",-")]
    size_label_tokens = {lbl.lower() for lbl in REAR_SIZE_LABELS.values()}
    for tok in tokens:
        if tok.lower() in size_label_tokens:
            continue
        t_tok = normalize_rear_texture(tok)
        if t_tok:
            return t_tok
    return ""


def fuse_rear_size_and_texture(size_label: str, texture: str = "") -> str:
    """Combines rear size and texture into a crisp 2-word phrase (e.g., 'Plush Plump'), never repeating 'Rear'."""
    bare_size = strip_rear_texture_from_size(size_label) or normalize_rear_size_label(size_label)
    norm_t = normalize_rear_texture(texture)
    if not bare_size and not norm_t:
        return ""
    if not norm_t:
        return bare_size
    if not bare_size:
        return norm_t
    if norm_t.lower() == bare_size.lower():
        return bare_size
    return f"{norm_t} {bare_size}"


def heal_character_rear_appearance(app_dict: Dict[str, Any], race: str = "") -> Dict[str, Any]:
    """Heals rear size/texture coherence on character read-hydration and strips feral myobu_fox rear fields."""
    if not isinstance(app_dict, dict):
        return app_dict
    if is_feral_rear_excluded(race):
        app_dict.pop("rear_size", None)
        app_dict.pop("rear_texture", None)
        return app_dict
    raw_rear = str(app_dict.get("rear_size") or "").strip()
    if not raw_rear:
        app_dict.pop("rear_size", None)
        app_dict.pop("rear_texture", None)
        return app_dict
    r_tier = classify_rear_size_tier(raw_rear)
    old_r_tex = str(app_dict.get("rear_texture") or "")
    source_tex = old_r_tex or extract_rear_texture(raw_rear)
    healed_r_tex = heal_rear_texture_for_context(source_tex, size_tier=r_tier) if source_tex else ""
    norm_r_lbl = normalize_rear_size_label(raw_rear) or raw_rear
    if healed_r_tex:
        app_dict["rear_texture"] = healed_r_tex
        fused_rear = fuse_rear_size_and_texture(norm_r_lbl, healed_r_tex)
        if fused_rear:
            app_dict["rear_size"] = fused_rear
    else:
        app_dict.pop("rear_texture", None)
        if norm_r_lbl:
            app_dict["rear_size"] = norm_r_lbl
    return app_dict


def roll_dynamic_rear_size(
    physique: str = "Average",
    gender: str = "female",
    race: str = "",
    hash_val: int = 0,
    seed: Any = None,
) -> str:
    """Physique- x gender-weighted procedural rear size roll. Caps Orang Bunian below Bountiful; skips feral myobu_fox."""
    if is_feral_rear_excluded(race):
        return ""
    raw_seed = seed if seed is not None else hash_val
    try:
        eff_seed = int(raw_seed or 0)
    except (ValueError, TypeError):
        eff_seed = int(hashlib.md5(str(raw_seed).encode("utf-8")).hexdigest()[:8], 16)

    canon_phys = normalize_physique(physique) or "Average"
    g_low = str(gender or "female").strip().lower()
    is_male = is_male_gender(g_low)

    if canon_phys == "Slim":
        weights = {"Flat": 18.0, "Compact": 42.0, "Shapely": 30.0, "Plump": 8.0, "Bountiful": 2.0}
    elif canon_phys in ("Athletic", "Muscular"):
        weights = {"Flat": 6.0, "Compact": 26.0, "Shapely": 48.0, "Plump": 16.0, "Bountiful": 4.0}
    elif canon_phys == "Voluptuous":
        weights = {"Flat": 0.0, "Compact": 4.0, "Shapely": 24.0, "Plump": 44.0, "Bountiful": 28.0}
    elif canon_phys == "Chubby":
        weights = {"Flat": 0.0, "Compact": 4.0, "Shapely": 20.0, "Plump": 42.0, "Bountiful": 34.0}
    elif canon_phys == "Stocky":
        weights = {"Flat": 4.0, "Compact": 18.0, "Shapely": 40.0, "Plump": 28.0, "Bountiful": 10.0}
    else:  # Average
        weights = {"Flat": 8.0, "Compact": 26.0, "Shapely": 42.0, "Plump": 18.0, "Bountiful": 6.0}

    if is_male:
        weights["Flat"] *= 1.4
        weights["Compact"] *= 1.35
        weights["Shapely"] *= 1.0
        weights["Plump"] *= 0.45
        weights["Bountiful"] *= 0.25

    if "bunian" in str(race or "").lower():
        weights["Bountiful"] = 0.0

    total = sum(weights.values())
    if total <= 0:
        return "Shapely"
    roll = (((abs(eff_seed) * 1103515245 + 12345) % 10000) / 10000.0) * total
    acc = 0.0
    for lbl, w in weights.items():
        if w <= 0:
            continue
        acc += w
        if roll <= acc:
            return lbl
    return "Shapely"


def roll_dynamic_rear_texture(
    hash_val: int = 0,
    size_tier: str = "average",
    physique: str = "",
    gender: str = "",
    race: str = "",
    seed: Any = None,
) -> str:
    """Rolls a canonical single-word rear texture compatible with size tier and physique."""
    if is_feral_rear_excluded(race):
        return ""
    raw_seed = seed if seed is not None else hash_val
    try:
        eff_seed = int(raw_seed or 0)
    except (ValueError, TypeError):
        eff_seed = int(hashlib.md5(str(raw_seed).encode("utf-8")).hexdigest()[:8], 16)

    raw_t = str(size_tier or "average").strip().lower()
    tier = raw_t if raw_t in REAR_SIZE_TIERS else classify_rear_size_tier(raw_t)
    incompat = REAR_TIER_INCOMPATIBLE_TEXTURES.get(tier, set())
    candidate_pool = [t for t in REAR_ASSET_TEXTURES if t not in incompat] or list(REAR_ASSET_TEXTURES)

    weights: Dict[str, float] = {t: 1.0 for t in candidate_pool}

    if tier in ("flat", "small"):
        for k, m in (("Firm", 1.5), ("Taut", 1.5), ("Supple", 1.3)):
            if k in weights:
                weights[k] *= m
    elif tier in ("large", "huge"):
        for k, m in (("Plush", 1.6), ("Jiggly", 1.5), ("Rounded", 1.5)):
            if k in weights:
                weights[k] *= m
    else:
        for k, m in (("Supple", 1.4), ("Rounded", 1.4)):
            if k in weights:
                weights[k] *= m

    p_low = str(physique or "").strip().lower()
    if any(k in p_low for k in ("athletic", "muscular", "slim", "toned", "fit")):
        for k, m in (("Firm", 1.6), ("Taut", 1.5)):
            if k in weights:
                weights[k] *= m
    elif any(k in p_low for k in ("voluptuous", "chubby", "plump", "curvy")):
        for k, m in (("Plush", 1.6), ("Jiggly", 1.5), ("Rounded", 1.4)):
            if k in weights:
                weights[k] *= m
    elif "stocky" in p_low:
        for k, m in (("Firm", 1.3), ("Rounded", 1.3), ("Supple", 1.2)):
            if k in weights:
                weights[k] *= m
    else:
        for k, m in (("Supple", 1.3), ("Rounded", 1.3)):
            if k in weights:
                weights[k] *= m

    g_low = str(gender or "").strip().lower()
    is_male = is_male_gender(g_low)
    if is_male:
        for k, m in (("Firm", 1.35), ("Taut", 1.35), ("Supple", 1.15)):
            if k in weights:
                weights[k] *= m

    total = sum(weights.values())
    if total <= 0:
        return candidate_pool[0]
    roll = (((abs(eff_seed) * 1664525 + 1013904223) % 10000) / 10000.0) * total
    acc = 0.0
    for t in candidate_pool:
        acc += weights.get(t, 1.0)
        if roll <= acc:
            return t
    return candidate_pool[-1]


def heal_intimate_preferences_surgically(appr: Dict[str, Any], gender: str = "") -> Dict[str, Any]:
    """Surgically heals legacy preference contradictions without mutating established experience tracks or kinks.
    - Strips biologically impossible female `Giving anal intimacy`.
    - Removes direct `act_likes` <-> `turn_offs` and `act_likes` <-> `act_dislikes` collisions.
    """
    if not isinstance(appr, dict):
        return appr
    raw_g = str(gender or appr.get("gender") or appr.get("sex") or "").strip().lower()
    if not raw_g:
        if appr.get("breast_size") and not appr.get("penis_size"):
            raw_g = "female"
        elif appr.get("penis_size") and not appr.get("breast_size"):
            raw_g = "male"
    is_fem = is_female_gender(raw_g)

    raw_likes = clean_attribute_list_string(appr.get("act_likes"))
    raw_dislikes = clean_attribute_list_string(appr.get("act_dislikes"))
    raw_turn_offs = clean_attribute_list_string(appr.get("turn_offs") or appr.get("aversions") or appr.get("dislikes_intimate"))

    name_to_id = {item["name"].lower(): item["id"] for item in ACT_PREFERENCE_REGISTRY}
    blocked_ids: set[str] = set()
    if is_fem:
        blocked_ids.update(FEMALE_EXCLUDED_ACT_IDS)

    if raw_turn_offs:
        to_l = raw_turn_offs.lower()
        from .generation import _turn_off_matches_key
        for to_name, conflict_ids in TURN_OFF_VS_ACT_LIKE_CONFLICTS.items():
            if _turn_off_matches_key(to_name, to_l):
                blocked_ids.update(conflict_ids)

    disliked_items_lower = {x.strip().lower() for x in raw_dislikes.split(",") if x.strip()} if raw_dislikes else set()

    if raw_likes:
        healed_likes = []
        for item in [x.strip() for x in raw_likes.split(",") if x.strip()]:
            il = item.lower()
            aid = name_to_id.get(il, il)
            if aid in blocked_ids or any(bid in il for bid in blocked_ids):
                continue
            if il in disliked_items_lower:
                continue
            healed_likes.append(item)
        appr["act_likes"] = ", ".join(healed_likes)

    if is_fem and raw_dislikes:
        healed_dislikes = [
            item for item in [x.strip() for x in raw_dislikes.split(",") if x.strip()]
            if name_to_id.get(item.lower(), item.lower()) not in FEMALE_EXCLUDED_ACT_IDS
        ]
        appr["act_dislikes"] = ", ".join(healed_dislikes)

    return appr


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
    is_male = is_male_gender(raw_g)

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
    is_male = is_male_gender(raw_g)

    raw_phys = str(app_dict.get("physique") or "").strip()
    if not raw_phys and extracted_app.get("physique"):
        raw_phys = str(extracted_app["physique"]).strip()

    physique = heal_physique_for_context(raw_phys, gender=raw_g, stature=stature, race=race) if raw_phys else ""
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

    # Scenario-gated NSFW body attributes (height preferences alone are SFW-safe and must not trigger NSFW hydration)
    _raw_bl_chk = app_dict.get("body_likes")
    _raw_bd_chk = app_dict.get("body_dislikes")
    _has_erotic_body_prefs = any(
        str(x).strip().lower().endswith(("_bb", "_ass"))
        for x in (
            (list(_raw_bl_chk) if isinstance(_raw_bl_chk, (list, tuple, set)) else [])
            + (list(_raw_bd_chk) if isinstance(_raw_bd_chk, (list, tuple, set)) else [])
        )
    )
    has_explicit_intimate = _has_erotic_body_prefs or any(
        app_dict.get(k) for k in (
            "breast_size", "penis_size", "asset_texture", "rear_size", "rear_texture",
            "turn_ons", "sensitive_spots",
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
                result["penis_size"] = roll_dynamic_penis_size(stature=stature, race=race, hash_val=hash_val)
            demeanor_fallback = infer_intimate_demeanor_from_traits(desc=desc, race=race, gender="male", traits=effective_traits, role=effective_role)
            dynamic_fallback = infer_intimate_dynamic_from_traits(desc=desc, race=race, gender="male", traits=effective_traits, role=effective_role)
        else:
            if b_size:
                result["breast_size"] = b_size
            else:
                result["breast_size"] = roll_dynamic_breast_size(physique=physique, hash_val=hash_val)
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
        raw_tex = app_dict.get("asset_texture")
        eff_gender = "male" if is_male else "female"

        raw_tex_low = str(raw_tex or "").strip().lower()
        is_gender_incompatible = False
        if raw_tex_low:
            if is_male and any(w in raw_tex_low for w in ("teardrop", "perky", "bouncy", "pillowy", "plush", "delicate", "chest fur", "underbelly down", "buoyant", "plumage")):
                is_gender_incompatible = True
            elif not is_male and any(w in raw_tex_low for w in ("veined", "curved", "tapered", "pulsing", "formidable", "ringed base")):
                is_gender_incompatible = True

        tex_val = ""
        if not is_gender_incompatible and raw_tex and str(raw_tex).strip().lower() not in ("none", "unknown", "", "auto", "__auto__"):
            tex_val = heal_asset_texture_for_context(raw_tex, gender=eff_gender, size_tier=curr_tier)
        if not tex_val and not raw_tex:
            extracted_tex = extract_asset_texture(result.get("penis_size" if is_male else "breast_size", ""), eff_gender)
            if extracted_tex:
                tex_val = heal_asset_texture_for_context(extracted_tex, gender=eff_gender, size_tier=curr_tier)

        if not tex_val:
            tex_val = roll_dynamic_asset_texture(
                hash_val,
                gender=eff_gender,
                race=race,
                physique=physique,
                demeanor=result.get("intimate_demeanor", ""),
                size_tier=curr_tier,
            )
        if tex_val:
            result["asset_texture"] = str(tex_val).strip()
            if is_male and result.get("penis_size"):
                result["penis_size"] = fuse_asset_size_and_texture(result["penis_size"], result["asset_texture"], gender="male")
            elif not is_male and result.get("breast_size"):
                result["breast_size"] = fuse_asset_size_and_texture(result["breast_size"], result["asset_texture"], gender="female")

        # Dynamic procedural generator for fallback with dynamic synergy
        dyn_intimate = generate_dynamic_intimate_attributes(
            hash_val,
            race=race,
            gender=gender,
            dynamic=result["intimate_dynamic"],
            openness=result["erotic_openness"],
            traits=effective_traits,
        )

        # Rear / Ass anatomy (all humanoids & anthropomorphic beastfolk; skipped for feral myobu_fox)
        if is_feral_rear_excluded(race):
            result.pop("rear_size", None)
            result.pop("rear_texture", None)
            result.pop("body_likes", None)
            result.pop("body_dislikes", None)
        else:
            raw_rear_size = _clean_nsfw_val(app_dict.get("rear_size"))
            norm_rear_size = normalize_rear_size_label(raw_rear_size) if raw_rear_size else ""
            if not norm_rear_size:
                norm_rear_size = roll_dynamic_rear_size(physique=physique, gender=eff_gender, race=race, hash_val=hash_val)
            rear_tier = classify_rear_size_tier(norm_rear_size)
            raw_r_tex = app_dict.get("rear_texture")
            r_tex_val = ""
            if raw_r_tex and str(raw_r_tex).strip().lower() not in ("none", "unknown", "", "auto", "__auto__"):
                r_tex_val = heal_rear_texture_for_context(raw_r_tex, size_tier=rear_tier)
            if not r_tex_val and raw_rear_size and not (raw_r_tex and str(raw_r_tex).strip().lower() in ("auto", "__auto__")):
                extracted_r_tex = extract_rear_texture(raw_rear_size)
                if extracted_r_tex:
                    r_tex_val = heal_rear_texture_for_context(extracted_r_tex, size_tier=rear_tier)
            if not r_tex_val:
                r_tex_val = roll_dynamic_rear_texture(
                    hash_val,
                    size_tier=rear_tier,
                    physique=physique,
                    gender=eff_gender,
                    race=race,
                )
            if r_tex_val:
                result["rear_texture"] = str(r_tex_val).strip()
                result["rear_size"] = fuse_rear_size_and_texture(norm_rear_size, result["rear_texture"])
            else:
                result["rear_size"] = norm_rear_size

            # Body preferences (BB & Ass size likes/dislikes): preserve explicit empty [] lists; lazy-seed only when absent
            has_explicit_body_prefs = (
                ("body_likes" in app_dict and app_dict["body_likes"] is not None)
                or ("body_dislikes" in app_dict and app_dict["body_dislikes"] is not None)
            )
            if has_explicit_body_prefs:
                clean_b_likes, clean_b_dislikes = normalize_body_preferences(
                    app_dict.get("body_likes"),
                    app_dict.get("body_dislikes"),
                )
                result["body_likes"] = clean_b_likes
                result["body_dislikes"] = clean_b_dislikes
            else:
                result["body_likes"] = list(dyn_intimate.get("body_likes") or [])
                result["body_dislikes"] = list(dyn_intimate.get("body_dislikes") or [])

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

    # Height preferences (SFW-safe: seeded once across both SFW & NSFW unless feral myobu_fox)
    _is_nsfw_ctx = bool(is_nsfw_scenario(scen_key) or has_explicit_intimate)
    _existing_likes, _existing_dislikes = normalize_body_preferences(
        result.get("body_likes") if "body_likes" in result else app_dict.get("body_likes"),
        result.get("body_dislikes") if "body_dislikes" in result else app_dict.get("body_dislikes"),
    )
    if is_feral_rear_excluded(race):
        result.pop("body_likes", None)
        result.pop("body_dislikes", None)
        result.pop("height_pref_seeded", None)
    else:
        if not _is_nsfw_ctx:
            _existing_likes = [k for k in _existing_likes if k in HEIGHT_PREFERENCE_KEYS]
            _existing_dislikes = [k for k in _existing_dislikes if k in HEIGHT_PREFERENCE_KEYS]
        _height_seeded = bool(app_dict.get("height_pref_seeded")) or any(
            k in HEIGHT_PREFERENCE_KEYS for k in (_existing_likes + _existing_dislikes)
        )
        if not _height_seeded:
            _h_seeded = generate_dynamic_height_preference(
                hash_val,
                gender=(gender or raw_g),
                stature=stature,
                race=race,
            )
            _existing_likes.extend(_h_seeded.get("body_likes") or [])
            _existing_dislikes.extend(_h_seeded.get("body_dislikes") or [])
            _existing_likes, _existing_dislikes = normalize_body_preferences(_existing_likes, _existing_dislikes)
        result["body_likes"] = _existing_likes
        result["body_dislikes"] = _existing_dislikes
        result["height_pref_seeded"] = True

    # Preserve all revealed flags and metadata state from input dictionary
    for flag_k in (
        "social_flags",
        "intimate_revealed", "intercourse_revealed", "oral_revealed", "manual_revealed",
        "demeanor_revealed", "dynamic_revealed", "openness_revealed",
        "sensitive_spots_revealed", "turn_ons_revealed", "turn_offs_revealed", "fetishes_revealed",
        "act_preferences_revealed", "body_preferences_revealed", "mannerisms_revealed", "underwear_revealed", "all_revealed",
        "had_first_time_with_player", "intimate_memories", "past_intimate_history", "past_intimate_entries"
    ):
        if flag_k in app_dict:
            result[flag_k] = app_dict[flag_k]

    for _fk in (
        "tail_count", "tails_description", "ears", "fur_coat", "skin_tone",
        "build", "body_type", "outfit_summary", "humanoid_outfit", "kitsune_form",
    ):
        if _fk in app_dict:
            result[_fk] = app_dict[_fk]
    result = enforce_intimacy_safeguard_invariants(result, gender=gender)
    if _is_nsfw_ctx:
        result = heal_intimate_preferences_surgically(result, gender=gender)
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
    if merged.get("physique"):
        norm_existing_p = normalize_physique(merged["physique"])
        if norm_existing_p:
            merged["physique"] = norm_existing_p
    if not incoming_app or not isinstance(incoming_app, dict):
        return merged

    # 1. Snapshot one-way reveal flags BEFORE merging
    _one_way_true_flags = (
        "intercourse_revealed", "oral_revealed", "manual_revealed", "anal_revealed",
        "intimate_revealed", "demeanor_revealed", "dynamic_revealed", "openness_revealed",
        "sensitive_spots_revealed", "turn_ons_revealed", "turn_offs_revealed", "fetishes_revealed",
        "act_preferences_revealed", "body_preferences_revealed", "height_pref_seeded", "underwear_revealed", "had_first_time_with_player", "all_revealed", "mannerisms_revealed"
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
        elif k in ("body_likes", "body_dislikes"):
            if k not in merged or merged.get(k) is None:
                c_likes, c_dislikes = normalize_body_preferences(
                    v if k == "body_likes" else merged.get("body_likes"),
                    v if k == "body_dislikes" else merged.get("body_dislikes"),
                )
                if k == "body_likes":
                    merged["body_likes"] = c_likes
                else:
                    merged["body_dislikes"] = c_dislikes
            elif (
                not existing_app.get("height_pref_seeded")
                and incoming_app.get("height_pref_seeded")
                and isinstance(v, list)
            ):
                has_merged_height = any(
                    str(hk).strip().lower() in HEIGHT_PREFERENCE_KEYS
                    for hk in (list(merged.get("body_likes") or []) + list(merged.get("body_dislikes") or []))
                )
                if not has_merged_height:
                    h_incoming = [x for x in v if str(x).strip().lower() in HEIGHT_PREFERENCE_KEYS]
                    if h_incoming:
                        base_likes = list(merged.get("body_likes") or []) + (h_incoming if k == "body_likes" else [])
                        base_dislikes = list(merged.get("body_dislikes") or []) + (h_incoming if k == "body_dislikes" else [])
                        c_likes, c_dislikes = normalize_body_preferences(base_likes, base_dislikes)
                        merged["body_likes"] = c_likes
                        merged["body_dislikes"] = c_dislikes
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

    if merged.get("physique"):
        norm_merged_p = normalize_physique(merged["physique"])
        if norm_merged_p:
            merged["physique"] = norm_merged_p

    if merged.get("asset_texture"):
        merged_g = str(merged.get("gender") or "")
        is_merged_m = any(kw in merged_g.lower() for kw in ("male", "man", "boy")) and "female" not in merged_g.lower()
        merged_size = merged.get("penis_size" if is_merged_m else "breast_size", "")
        merged_tier = classify_asset_size_tier(str(merged_size or ""), "male" if is_merged_m else "female")
        healed_tex = heal_asset_texture_for_context(
            merged["asset_texture"],
            gender="male" if is_merged_m else "female",
            size_tier=merged_tier,
        )
        if healed_tex:
            merged["asset_texture"] = healed_tex

    if merged.get("rear_texture"):
        rear_tier = classify_rear_size_tier(str(merged.get("rear_size") or ""))
        healed_r_tex = heal_rear_texture_for_context(merged["rear_texture"], size_tier=rear_tier)
        if healed_r_tex:
            merged["rear_texture"] = healed_r_tex
            if merged.get("rear_size"):
                merged["rear_size"] = fuse_rear_size_and_texture(str(merged["rear_size"]), healed_r_tex)

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
from .generation import generate_dynamic_intimate_attributes, generate_dynamic_height_preference, normalize_body_preferences
