"""mechanics/memory — Hierarchical Long-Term Memory Engine for Hikayat."""
from __future__ import annotations

from .digest import should_trigger_digest, generate_arc_digest, fire_digest_if_needed
from .budget import DynamicTokenBudget, SceneMode
from .tokenization import (
    extract_cjk_bigrams,
    fold_diacritics,
    sanitize_fts_query,
    score_digest_candidates,
    tokenize_for_fts,
)
from .vector import cosine_similarity, hybrid_search

__all__ = [
    "should_trigger_digest",
    "generate_arc_digest",
    "fire_digest_if_needed",
    "DynamicTokenBudget",
    "SceneMode",
    "extract_cjk_bigrams",
    "fold_diacritics",
    "sanitize_fts_query",
    "score_digest_candidates",
    "tokenize_for_fts",
    "cosine_similarity",
    "hybrid_search",
]
