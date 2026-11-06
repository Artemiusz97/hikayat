from __future__ import annotations
"""
Pure 5-language + CJK tokenization and 2-signal entity/BM25 scoring for Hikayat memory recall.
Layer 2 (Deterministic Mechanics) — zero SQLite or network dependencies.
"""
import re
import unicodedata

_CJK_CHAR_CLASS = r"\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af"
_CJK_RE = re.compile(f"[{_CJK_CHAR_CLASS}]")
_CJK_RUN_RE = re.compile(f"[{_CJK_CHAR_CLASS}]+")

_SPECIAL_LATIN_MAP = str.maketrans({
    "ł": "l", "Ł": "l",
    "ß": "ss", "ẞ": "ss",
    "đ": "d", "Đ": "d",
    "ø": "o", "Ø": "o",
    "æ": "ae", "Æ": "ae",
    "œ": "oe", "Œ": "oe",
})

STOPWORDS: frozenset[str] = frozenset({
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are", "as", "at",
    "be", "because", "been", "before", "being", "below", "between", "both", "but", "by", "cannot", "could",
    "did", "do", "does", "doing", "down", "during", "each", "few", "for", "from", "further", "had", "has",
    "have", "having", "he", "her", "here", "hers", "herself", "him", "himself", "his", "how", "i", "if",
    "in", "into", "is", "it", "its", "itself", "me", "more", "most", "my", "myself", "no", "nor", "not",
    "of", "off", "on", "once", "only", "or", "other", "ought", "our", "ours", "ourselves", "out", "over",
    "own", "same", "she", "should", "so", "some", "such", "than", "that", "the", "their", "theirs", "them",
    "themselves", "then", "there", "these", "they", "this", "those", "through", "to", "too", "under",
    "until", "up", "very", "was", "we", "were", "what", "when", "where", "which", "while", "who", "whom",
    "why", "with", "would", "you", "your", "yours", "yourself", "yourselves", "near",
})


def fold_diacritics(text: str) -> str:
    """Fold Latin diacritics and stroked letters (e.g. 'żółty' -> 'zolty', 'Schlüssel' -> 'schlussel')
    while preserving CJK codepoints intact.
    """
    if not text:
        return ""
    mapped = text.translate(_SPECIAL_LATIN_MAP)
    out: list[str] = []
    for ch in mapped:
        if _CJK_RE.match(ch):
            out.append(ch)
        else:
            decomp = unicodedata.normalize("NFKD", ch)
            out.append("".join(c for c in decomp if not unicodedata.combining(c)))
    return "".join(out)


def extract_cjk_bigrams(text: str, include_unigrams: bool = True) -> list[str]:
    """Extract CJK unigrams and overlapping bigrams from contiguous CJK runs."""
    if not text:
        return []
    tokens: list[str] = []
    for run in _CJK_RUN_RE.findall(text):
        n = len(run)
        if n == 1:
            tokens.append(run)
        else:
            for i in range(n):
                if include_unigrams:
                    tokens.append(run[i])
                if i + 1 < n:
                    tokens.append(run[i : i + 2])
    return tokens


def tokenize_for_fts(text: str) -> str:
    """Normalize arbitrary multilingual text into whitespace-delimited FTS5 index tokens."""
    if not text:
        return ""
    folded = fold_diacritics(text.lower())
    clean_latin = re.sub(f"[^\\w\\s{_CJK_CHAR_CLASS}]", " ", folded)
    latin_words = [
        w for w in re.sub(f"[{_CJK_CHAR_CLASS}]", " ", clean_latin).split()
        if w
    ]
    cjk_tokens = extract_cjk_bigrams(text, include_unigrams=True)
    return " ".join(latin_words + cjk_tokens)


def sanitize_fts_query(query_text: str, max_terms: int = 12) -> str:
    """Build a safe FTS5 MATCH expression supporting Latin prefix terms and 1+/2-char CJK words."""
    if not query_text or not query_text.strip():
        return ""
    folded = fold_diacritics(query_text.lower())
    clean_latin = re.sub(f"[^\\w\\s{_CJK_CHAR_CLASS}]", " ", folded)
    latin_terms = [
        w for w in re.sub(f"[{_CJK_CHAR_CLASS}]", " ", clean_latin).split()
        if len(w) >= 2 and w not in STOPWORDS
    ]
    # Prefer bigrams on >=2-char CJK runs so 2-char words ('铁剑', '客栈') match precisely without single-char stopword noise
    cjk_terms = extract_cjk_bigrams(query_text, include_unigrams=False)

    seen: set[str] = set()
    clauses: list[str] = []
    for term in cjk_terms + latin_terms:
        t = term.replace('"', "").strip()
        if not t or t in seen:
            continue
        seen.add(t)
        if _CJK_RE.search(t):
            clauses.append(f'"{t}"')
        else:
            clauses.append(f'"{t}"*')
        if len(clauses) >= max_terms:
            break
    return " OR ".join(clauses)


def score_digest_candidates(
    digest_rows: list[dict],
    fts_ranks: dict[str, float],
    present_npcs: list[str] | None = None,
    current_location: str = "",
    active_quest_ids: list[str] | None = None,
    limit: int = 6,
) -> list[str]:
    """Rank historic digest bullets using 2-signal scoring:
      Signal 1 (0.6): Entity / Location / Quest overlap with current scene
      Signal 2 (0.4): FTS5 BM25 reciprocal rank
    """
    target_npcs = {str(n).strip().lower() for n in (present_npcs or []) if n and str(n).strip()}
    target_quests = {str(q).strip().lower() for q in (active_quest_ids or []) if q and str(q).strip()}
    loc_clean = str(current_location or "").strip().lower()

    candidate_scores: dict[str, float] = {}

    for row in digest_rows:
        bullets = row.get("bullets") or []
        entities = {str(e).strip().lower() for e in (row.get("entities") or []) if e}
        quests = {str(q).strip().lower() for q in (row.get("quest_ids") or []) if q}
        arc_loc = str(row.get("location_tag") or "").strip().lower()

        overlap_score = 0.0
        if target_npcs:
            npc_hits = len(target_npcs.intersection(entities))
            if npc_hits > 0:
                overlap_score += min(1.0, npc_hits * 0.5)
        if target_quests and target_quests.intersection(quests):
            overlap_score += 0.35
        if loc_clean and arc_loc and len(arc_loc) >= 3 and (loc_clean in arc_loc or arc_loc in loc_clean):
            overlap_score += 0.25
        overlap_score = min(1.0, overlap_score)

        for b in bullets:
            if not isinstance(b, str) or not b.strip():
                continue
            b_clean = b.strip()
            # Also detect direct present-NPC name mention inside bullet text for legacy rows lacking entities_json
            bullet_npc_bonus = 0.0
            if target_npcs and overlap_score == 0.0:
                b_low = b_clean.lower()
                if any(npc in b_low for npc in target_npcs if len(npc) >= 3):
                    bullet_npc_bonus = 0.45

            eff_overlap = min(1.0, overlap_score + bullet_npc_bonus)
            fts_score = fts_ranks.get(b_clean, 0.0)
            final_score = (0.6 * eff_overlap) + (0.4 * fts_score)
            if final_score > 0.05:
                if final_score > candidate_scores.get(b_clean, 0.0):
                    candidate_scores[b_clean] = final_score

    # Include any FTS hits not in the recent 30 digest_rows slice
    for b_text, f_rank in fts_ranks.items():
        if b_text not in candidate_scores and (0.4 * f_rank) > 0.05:
            candidate_scores[b_text] = 0.4 * f_rank

    ranked = sorted(candidate_scores.items(), key=lambda kv: kv[1], reverse=True)
    return [b for b, _ in ranked[:limit]]
