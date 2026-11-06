"""Offline cosine-similarity & RRF math helpers preserved for backwards-compatible callers and tests.

Note: Production episodic recall switched to zero-HTTP deterministic 2-Signal FTS5 + metadata affinity
in Migration 37 (`db/memory.py:recall_chapter_digests`).
"""
from __future__ import annotations

import math
from typing import List, Tuple


def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot_product = sum(a * b for a, b in zip(v1, v2))
    norm_v1 = math.sqrt(sum(a * a for a in v1))
    norm_v2 = math.sqrt(sum(b * b for b in v2))
    if norm_v1 == 0 or norm_v2 == 0:
        return 0.0
    return dot_product / (norm_v1 * norm_v2)


def hybrid_search(
    fts_results: List[str],
    vector_results: List[Tuple[str, List[float]]],
    query_embedding: List[float],
    alpha: float = 0.5,
    top_k: int = 6,
    min_similarity: float = 0.25,
) -> List[str]:
    """Backwards-compatible RRF combiner with deduplication and cosine similarity floor."""
    scores: dict[str, float] = {}
    seen_fts: set[str] = set()

    for rank, text in enumerate(fts_results or []):
        if not text or text in seen_fts:
            continue
        seen_fts.add(text)
        scores[text] = scores.get(text, 0.0) + (1.0 - alpha) * (1.0 / (rank + 60))

    if query_embedding and vector_results:
        best_sim_by_text: dict[str, float] = {}
        for text, emb in vector_results:
            if not text:
                continue
            sim = cosine_similarity(query_embedding, emb)
            if sim >= min_similarity and sim > best_sim_by_text.get(text, -1.0):
                best_sim_by_text[text] = sim

        vec_scores = sorted(best_sim_by_text.items(), key=lambda kv: kv[1], reverse=True)
        for rank, (text, _sim) in enumerate(vec_scores):
            scores[text] = scores.get(text, 0.0) + alpha * (1.0 / (rank + 60))

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    return [text for text, _score in ranked[:top_k]]
