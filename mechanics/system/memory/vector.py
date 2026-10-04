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
    top_k: int = 6
) -> List[str]:
    """
    Combine FTS5 results and Vector cosine similarity results using Reciprocal Rank Fusion (RRF)
    or a normalized score. We will just use RRF for simplicity, but boost vector scores.
    fts_results: list of strings (ordered by BM25 rank).
    vector_results: list of (text, embedding) tuples.
    """
    scores = {}
    
    # 1. Score FTS matches (RRF)
    for rank, text in enumerate(fts_results):
        scores[text] = scores.get(text, 0.0) + (1.0 - alpha) * (1.0 / (rank + 60))
        
    # 2. Score Vector matches
    if query_embedding and vector_results:
        # Calculate cosine similarity for all
        vec_scores = []
        for text, emb in vector_results:
            sim = cosine_similarity(query_embedding, emb)
            vec_scores.append((sim, text))
            
        # Sort by similarity
        vec_scores.sort(key=lambda x: x[0], reverse=True)
        
        for rank, (sim, text) in enumerate(vec_scores):
            # Add to RRF score
            scores[text] = scores.get(text, 0.0) + alpha * (1.0 / (rank + 60))
            
    # 3. Sort combined and return top_k
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [text for text, score in ranked[:top_k]]
