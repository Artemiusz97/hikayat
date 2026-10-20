from __future__ import annotations
"""
Centralized Locales and Multilingual Mechanics Hub.

Aggregates item lemmas, item icon keywords, two-handed indicators, affixes,
and intent phrases across all supported language modules.
"""
from typing import Dict, List, Optional, Tuple, Set

from . import en
from . import pl
from . import ms
from . import zh
from . import de

SUPPORTED_LOCALES: Tuple[str, ...] = ("en", "pl", "ms", "zh", "de")

LOCALES = {
    "en": en,
    "pl": pl,
    "ms": ms,
    "zh": zh,
    "de": de,
}

# 1. Affix Mappings
ALL_AFFIX_TRANSLATIONS: Dict[str, Dict[str, str]] = {
    lang: getattr(mod, "ENEMY_AFFIXES", {})
    for lang, mod in LOCALES.items()
}

# Reverse mapping: any localized affix lowercase -> Canonical English
CANONICAL_AFFIX_LOOKUP: Dict[str, str] = {}
for lang, locale_affixes in ALL_AFFIX_TRANSLATIONS.items():
    for en_affix, loc_affix in locale_affixes.items():
        CANONICAL_AFFIX_LOOKUP[loc_affix.lower()] = en_affix
        CANONICAL_AFFIX_LOOKUP[en_affix.lower()] = en_affix


def translate_affix(affix: str, language: str = "en") -> str:
    """Translates a canonical English affix to the target language, or returns original."""
    lang = (language or "en").lower().strip()
    return ALL_AFFIX_TRANSLATIONS.get(lang, {}).get(affix, affix)


def canonicalize_affix(affix: str) -> str:
    """Resolves a localized or canonical affix back to its canonical English form."""
    if not affix:
        return ""
    clean = affix.strip().lower()
    return CANONICAL_AFFIX_LOOKUP.get(clean, affix)


# 2. Item Icon Keywords (Aggregated across all supported locales)
# Maps category key -> unique tuple of keywords across all languages
ICON_KEYWORDS: Dict[str, Tuple[str, ...]] = {}

# Gather all unique categories defined across all locales
all_icon_categories: Set[str] = set()
for mod in LOCALES.values():
    if hasattr(mod, "ITEM_ICON_KEYWORDS"):
        all_icon_categories.update(mod.ITEM_ICON_KEYWORDS.keys())

for category in all_icon_categories:
    cat_keywords: List[str] = []
    for mod in LOCALES.values():
        mod_kw = getattr(mod, "ITEM_ICON_KEYWORDS", {}).get(category, ())
        for kw in mod_kw:
            if kw and kw not in cat_keywords:
                cat_keywords.append(kw)
    ICON_KEYWORDS[category] = tuple(cat_keywords)


def get_icon_keywords(category: str) -> Tuple[str, ...]:
    """Retrieves all localized keywords for an item icon category."""
    return ICON_KEYWORDS.get(category, ())


# 3. Two-Handed Equipment Keywords & Archetypes
_all_2h_keywords: List[str] = []
for mod in LOCALES.values():
    for kw in getattr(mod, "TWO_HANDED_KEYWORDS", ()):
        if kw and kw not in _all_2h_keywords:
            _all_2h_keywords.append(kw)
TWO_HANDED_KEYWORDS: Tuple[str, ...] = tuple(_all_2h_keywords)

_all_2h_archs: List[str] = []
for mod in LOCALES.values():
    for arch in getattr(mod, "TWO_HANDED_ARCHETYPES", ()):
        if arch and arch not in _all_2h_archs:
            _all_2h_archs.append(arch)
TWO_HANDED_ARCHETYPES: Tuple[str, ...] = tuple(_all_2h_archs)


# 4. Item Lemmas for Generation & Loot Parsing
def get_all_item_lemmas(category: str) -> List[str]:
    """Returns aggregated item lemmas for a specific category across non-English locales."""
    results = []
    for lang, mod in LOCALES.items():
        if lang == "en":
            continue
        lemmas = getattr(mod, "ITEM_LEMMAS", {})
        if category in lemmas:
            results.extend(lemmas[category])
    return results


# 5. Narrative Intent Phrases (Exits, Initiations, Movement)
_all_exits: List[str] = []
_all_inits: List[str] = []
_all_moves: List[str] = []

for mod in LOCALES.values():
    for phrase in getattr(mod, "DIALOGUE_EXIT_PHRASES", ()):
        if phrase and phrase not in _all_exits:
            _all_exits.append(phrase)
    for phrase in getattr(mod, "DIALOGUE_INIT_PREFIXES", ()):
        if phrase and phrase not in _all_inits:
            _all_inits.append(phrase)
    for phrase in getattr(mod, "MOVEMENT_PREFIXES", ()):
        if phrase and phrase not in _all_moves:
            _all_moves.append(phrase)

ALL_DIALOGUE_EXIT_PHRASES: Tuple[str, ...] = tuple(_all_exits)
ALL_DIALOGUE_INIT_PREFIXES: Tuple[str, ...] = tuple(_all_inits)
ALL_MOVEMENT_PREFIXES: Tuple[str, ...] = tuple(_all_moves)


def get_all_dialogue_exit_phrases() -> Tuple[str, ...]:
    """Returns dialogue exit phrases across non-English locales."""
    results = []
    for lang, mod in LOCALES.items():
        if lang == "en":
            continue
        results.extend(getattr(mod, "DIALOGUE_EXIT_PHRASES", ()))
    return tuple(results)


def get_all_dialogue_init_prefixes() -> Tuple[str, ...]:
    """Returns dialogue initiation prefixes across non-English locales."""
    results = []
    for lang, mod in LOCALES.items():
        if lang == "en":
            continue
        results.extend(getattr(mod, "DIALOGUE_INIT_PREFIXES", ()))
    return tuple(results)


def get_all_movement_prefixes() -> Tuple[str, ...]:
    """Returns movement prefixes across non-English locales."""
    results = []
    for lang, mod in LOCALES.items():
        if lang == "en":
            continue
        results.extend(getattr(mod, "MOVEMENT_PREFIXES", ()))
    return tuple(results)


__all__ = [
    "SUPPORTED_LOCALES",
    "LOCALES",
    "ALL_AFFIX_TRANSLATIONS",
    "CANONICAL_AFFIX_LOOKUP",
    "translate_affix",
    "canonicalize_affix",
    "ICON_KEYWORDS",
    "get_icon_keywords",
    "TWO_HANDED_KEYWORDS",
    "TWO_HANDED_ARCHETYPES",
    "get_all_item_lemmas",
    "ALL_DIALOGUE_EXIT_PHRASES",
    "ALL_DIALOGUE_INIT_PREFIXES",
    "ALL_MOVEMENT_PREFIXES",
    "get_all_dialogue_exit_phrases",
    "get_all_dialogue_init_prefixes",
    "get_all_movement_prefixes",
    "en",
    "pl",
    "ms",
]
