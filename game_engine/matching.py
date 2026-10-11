from __future__ import annotations
"""
Centralized Lexical Matching Engine for Hikayat.

Provides word-boundary matching with Scunthorpe collision prevention,
clause-aware negation detection, and compiled pattern caching.
"""
import re
import unicodedata
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Pattern, Sequence, Set, Tuple, Union

# Common English negation indicators and refusal markers
NEGATION_MARKERS: Set[str] = {
    "not", "don't", "dont", "never", "no", "cannot", "can't", "cant",
    "refuse", "refuses", "refused", "refusing",
    "stop", "stops", "stopped", "stopping",
    "without", "hardly", "barely",
    "won't", "wont", "wouldn't", "wouldnt",
    "shouldn't", "shouldnt", "couldn't", "couldnt",
    "isn't", "isnt", "aren't", "arent",
    "wasn't", "wasnt", "weren't", "werent",
    "didn't", "didnt", "doesn't", "doesnt"
}

# Punctuation and contrast words that reset the scope of a negation marker
_CLAUSE_BOUNDARY_RE = re.compile(r'[.,!?;:\n]|(?:\b(?:but|however|although|yet|except)\b)', re.IGNORECASE)

# Global pattern cache keyed by the sorted tuple of keywords
_KEYWORD_REGEX_CACHE: Dict[Tuple[str, ...], Pattern] = {}


@dataclass(frozen=True)
class MatchResult:
    """Detailed result of a keyword match inspection."""
    matched: bool = False
    is_negated: bool = False
    matched_term: str = ""
    span: Tuple[int, int] = (-1, -1)
    raw_match: str = ""


def normalize_text(text: str) -> str:
    """Standardizes Unicode (NFKC) and collapses internal whitespace sequences to a single space."""
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKC", str(text))
    return re.sub(r"\s+", " ", normalized).strip()


def _compile_keyword_regex(keywords: Sequence[str]) -> Pattern:
    """Builds a cached regex matching exact tokens on word boundaries, handling multi-word whitespace."""
    # Deduplicate and sort descending by length so longer phrases match before substrings
    cleaned = [k.strip() for k in keywords if k and k.strip()]
    sorted_keywords = tuple(sorted(set(cleaned), key=lambda x: len(x), reverse=True))
    
    cached = _KEYWORD_REGEX_CACHE.get(sorted_keywords)
    if cached is not None:
        return cached

    phrases = []
    for kw in sorted_keywords:
        tokens = kw.split()
        if not tokens:
            continue
        escaped_tokens = [re.escape(t) for t in tokens]
        phrases.append(r"\s+".join(escaped_tokens))

    if not phrases:
        pattern = r"$^"  # Matches nothing
    else:
        pattern = r"\b(?:" + "|".join(phrases) + r")\b"

    rx = re.compile(pattern, re.IGNORECASE)
    _KEYWORD_REGEX_CACHE[sorted_keywords] = rx
    return rx


def detect_negation(text: str, match_start: int, max_window_words: int = 5) -> bool:
    """
    Checks if a match starting at match_start is preceded by a negation marker in the same clause.
    Inspects up to max_window_words immediately preceding the match start.
    """
    if match_start <= 0 or not text:
        return False

    prefix = text[:match_start]
    
    # Find the nearest preceding clause boundary
    last_boundary_pos = 0
    for m in _CLAUSE_BOUNDARY_RE.finditer(prefix):
        last_boundary_pos = m.end()

    clause_prefix = prefix[last_boundary_pos:].strip()
    if not clause_prefix:
        return False

    # Extract preceding word tokens
    words = re.findall(r"\b[\w']+\b", clause_prefix.lower())
    if not words:
        return False

    # Check the window of words preceding the keyword
    preceding_window = words[-max_window_words:]
    return any(w in NEGATION_MARKERS for w in preceding_window)


def find_keyword_match(
    text: str,
    keywords: Sequence[str] | Set[str] | Tuple[str, ...],
    *,
    check_negation: bool = True,
    max_negation_window_words: int = 5
) -> MatchResult:
    """
    Scans text for any of the given keywords on word boundaries.
    Returns a MatchResult indicating match status, negation status, and location.
    """
    if not text or not keywords:
        return MatchResult()

    norm_text = normalize_text(text)
    rx = _compile_keyword_regex(tuple(keywords))
    match = rx.search(norm_text)
    
    if not match:
        return MatchResult()

    start, end = match.span()
    raw_match = match.group(0)
    
    is_negated = False
    if check_negation:
        is_negated = detect_negation(norm_text, start, max_window_words=max_negation_window_words)

    # Resolve which original keyword matched (normalized case-insensitive)
    matched_term = raw_match.lower()
    for kw in keywords:
        if normalize_text(kw).lower() == matched_term:
            matched_term = kw
            break

    return MatchResult(
        matched=True,
        is_negated=is_negated,
        matched_term=matched_term,
        span=(start, end),
        raw_match=raw_match
    )


def matches_keyword(
    text: str,
    keywords: Sequence[str] | Set[str] | Tuple[str, ...],
    *,
    allow_negated: bool = True,
    check_negation: bool = True
) -> bool:
    """
    Convenience boolean checker.
    If allow_negated is False, returns False when the match is preceded by a negation marker.
    """
    res = find_keyword_match(text, keywords, check_negation=check_negation or not allow_negated)
    if not res.matched:
        return False
    if not allow_negated and res.is_negated:
        return False
    return True


def matches_keyword_boundary(
    text: str,
    keywords: tuple[str, ...] | list[str] | Sequence[str],
    *,
    allow_negated: bool = True
) -> bool:
    """
    Word-boundary keyword matcher for backward compatibility with game_engine.keywords.
    Strictly prevents Scunthorpe collisions and optionally checks negation guards.
    """
    return matches_keyword(text, keywords, allow_negated=allow_negated)
