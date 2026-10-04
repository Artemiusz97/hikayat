"""
db/memory.py — Long-Term Memory CRUD Layer
==========================================
Provides persistence for the Hierarchical Memory Engine:
  - commitments_ledger: active promises, pacts, secrets, debts between player and NPCs.
  - session_digests / sessions.chapter_digest_json: episodic arc summaries (Tier 2 Memory).
"""
import json
import time
import logging

import db
from .core import get_conn

log = logging.getLogger("hikayat.db.memory")

# ---------------------------------------------------------------------------
# Commitments Ledger
# ---------------------------------------------------------------------------

VALID_COMMITMENT_TYPES = frozenset({"promise", "secret", "debt", "pact", "threat"})


def add_commitment(
    session_id: int,
    source_entity: str,
    target_entity: str,
    commitment_type: str,
    description: str,
    turn_number: int = 0,
) -> dict:
    """Record a new commitment (promise, pact, secret, etc.) between entities.

    Returns the newly inserted row as a dict, or {} on validation failure.
    """
    if not description or not description.strip():
        return {}
    commitment_type = commitment_type.lower().strip()
    if commitment_type not in VALID_COMMITMENT_TYPES:
        commitment_type = "promise"

    now = time.time()
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO commitments_ledger
               (session_id, source_entity, target_entity, commitment_type,
                description, status, turn_created, updated_at)
               VALUES (?, ?, ?, ?, ?, 'active', ?, ?)""",
            (
                session_id,
                (source_entity or "player").strip(),
                (target_entity or "player").strip(),
                commitment_type,
                description.strip(),
                turn_number,
                now,
            ),
        )
        row_id = cur.lastrowid
    return get_commitment(session_id, row_id)


def get_commitment(session_id: int, commitment_id: int) -> dict:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM commitments_ledger WHERE id=? AND session_id=?",
            (commitment_id, session_id),
        ).fetchone()
    return dict(row) if row else {}


def get_active_commitments(
    session_id: int,
    entity_name: str | None = None,
    limit: int = 10,
) -> list[dict]:
    """Return all active commitments for a session, optionally filtered to
    those involving a specific entity (as source OR target, case-insensitive).
    """
    with get_conn() as conn:
        if entity_name:
            name_lower = entity_name.strip().lower()
            rows = conn.execute(
                """SELECT * FROM commitments_ledger
                   WHERE session_id=? AND status='active'
                     AND (lower(source_entity)=? OR lower(target_entity)=?)
                   ORDER BY turn_created ASC LIMIT ?""",
                (session_id, name_lower, name_lower, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT * FROM commitments_ledger
                   WHERE session_id=? AND status='active'
                   ORDER BY turn_created ASC LIMIT ?""",
                (session_id, limit),
            ).fetchall()
    return [dict(r) for r in rows]


def update_commitment_status(
    session_id: int, commitment_id: int, status: str
) -> bool:
    """Update commitment status to 'fulfilled' or 'broken'. Returns True on success."""
    status = status.lower().strip()
    if status not in ("fulfilled", "broken", "active"):
        return False
    now = time.time()
    with get_conn() as conn:
        conn.execute(
            "UPDATE commitments_ledger SET status=?, updated_at=? WHERE id=? AND session_id=?",
            (status, now, commitment_id, session_id),
        )
    return True


def bulk_add_commitments(
    session_id: int,
    commitments: list[dict],
    turn_number: int = 0,
) -> int:
    """Bulk-insert a list of commitment dicts (from LLM digest output).
    Each dict must have: source_entity, target_entity, commitment_type, description.
    Returns number of successfully inserted rows.
    """
    inserted = 0
    for c in (commitments or []):
        if not isinstance(c, dict):
            continue
        result = add_commitment(
            session_id=session_id,
            source_entity=str(c.get("source_entity", "player")),
            target_entity=str(c.get("target_entity", "")),
            commitment_type=str(c.get("commitment_type", "promise")),
            description=str(c.get("description", "")),
            turn_number=turn_number,
        )
        if result:
            inserted += 1
    return inserted


# ---------------------------------------------------------------------------
# Chapter Digest (Tier 2 Memory)
# ---------------------------------------------------------------------------

# Maximum number of bullet-point strings kept in the rolling digest.
MAX_DIGEST_BULLETS = 30


def append_chapter_digest(
    session_id: int,
    turn_start: int,
    turn_end: int,
    bullets: list[str],
    embeddings: list[list[float]] = None
) -> list[str]:
    """Append new narrative bullet points to the session's rolling chapter digest.
    Also writes a row to session_digests for audit/debugging purposes.
    Returns the updated full list of digest bullets.
    """
    if not bullets:
        return get_chapter_digest(session_id)

    now = time.time()
    clean_bullets = [b.strip() for b in bullets if isinstance(b, str) and b.strip()]
    if not clean_bullets:
        return get_chapter_digest(session_id)

    # Store raw arc in session_digests for audit trail
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO session_digests
               (session_id, turn_start, turn_end, summary_bullets_json, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (session_id, turn_start, turn_end, json.dumps(clean_bullets), now),
        )
        # Also index immediately in FTS5 and Vectors
        for i, b in enumerate(clean_bullets):
            conn.execute(
                "INSERT INTO session_digests_fts (session_id, bullet_text) VALUES (?, ?)",
                (session_id, b)
            )
            if embeddings and i < len(embeddings) and embeddings[i]:
                conn.execute(
                    "INSERT INTO session_digest_vectors (session_id, bullet_text, vector_json) VALUES (?, ?, ?)",
                    (session_id, b, json.dumps(embeddings[i]))
                )

    # Update the rolling digest on sessions.chapter_digest_json
    current = get_chapter_digest(session_id)
    combined = current + clean_bullets
    # Keep only the most recent MAX_DIGEST_BULLETS entries
    trimmed = combined[-MAX_DIGEST_BULLETS:]

    with get_conn() as conn:
        conn.execute(
            "UPDATE sessions SET chapter_digest_json=? WHERE id=?",
            (json.dumps(trimmed), session_id),
        )
    return trimmed

def remove_oldest_chapter_digest_bullets(session_id: int, count: int):
    """Remove the oldest N bullets from the active rolling digest after Tier 3 compaction."""
    current = get_chapter_digest(session_id)
    if not current or count <= 0:
        return
    trimmed = current[count:]
    with get_conn() as conn:
        conn.execute(
            "UPDATE sessions SET chapter_digest_json=? WHERE id=?",
            (json.dumps(trimmed), session_id),
        )


def get_chapter_digest(session_id: int) -> list[str]:
    """Return the current list of chapter digest bullet strings for a session."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT chapter_digest_json FROM sessions WHERE id=?",
            (session_id,),
        ).fetchone()
    if not row:
        return []
    raw = row["chapter_digest_json"] or "[]"
    try:
        result = json.loads(raw)
        return result if isinstance(result, list) else []
    except Exception:
        return []


def search_chapter_digests(session_id: int, query_text: str, limit: int = 6, query_embedding: list[float] = None) -> list[str]:
    """Search older chapter digest bullets using FTS5 BM25 relevance matching."""
    if not query_text or not query_text.strip():
        return []
        
    import re
    # Extensive English stopword list to prevent generic words from polluting BM25 ranking
    STOPWORDS = {
        "a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are", "aren't", "as", "at", 
        "be", "because", "been", "before", "being", "below", "between", "both", "but", "by", "can't", "cannot", "could", 
        "couldn't", "did", "didn't", "do", "does", "doesn't", "doing", "don't", "down", "during", "each", "few", "for", 
        "from", "further", "had", "hadn't", "has", "hasn't", "have", "haven't", "having", "he", "he'd", "he'll", "he's", 
        "her", "here", "here's", "hers", "herself", "him", "himself", "his", "how", "how's", "i", "i'd", "i'll", "i'm", 
        "i've", "if", "in", "into", "is", "isn't", "it", "it's", "its", "itself", "let's", "me", "more", "most", "mustn't", 
        "my", "myself", "no", "nor", "not", "of", "off", "on", "once", "only", "or", "other", "ought", "our", "ours", 
        "ourselves", "out", "over", "own", "same", "shan't", "she", "she'd", "she'll", "she's", "should", "shouldn't", "so", 
        "some", "such", "than", "that", "that's", "the", "their", "theirs", "them", "themselves", "then", "there", "there's", 
        "these", "they", "they'd", "they'll", "they're", "they've", "this", "those", "through", "to", "too", "under", "until", 
        "up", "very", "was", "wasn't", "we", "we'd", "we'll", "we're", "we've", "were", "weren't", "what", "what's", "when", 
        "when's", "where", "where's", "which", "while", "who", "who's", "whom", "why", "why's", "with", "won't", "would", 
        "wouldn't", "you", "you'd", "you'll", "you're", "you've", "your", "yours", "yourself", "yourselves", "near"
    }

    # Sanitize FTS query to prevent syntax errors: remove punctuation, quotes, and boolean operators
    sanitized = re.sub(r'[^\w\s]', ' ', query_text.lower())
    words = [w for w in sanitized.split() if w and w not in STOPWORDS and len(w) > 2]
    if not words:
        return []
        
    # Build a prefix-match FTS5 query: "term1*" OR "term2*"
    fts_query = " OR ".join(f'"{w}"*' for w in words[:10])  # Cap at 10 words to prevent query explosion
    
    with get_conn() as conn:
        try:
            fts_rows = conn.execute(
                """SELECT bullet_text FROM session_digests_fts 
                   WHERE session_id=? AND session_digests_fts MATCH ? 
                   ORDER BY rank LIMIT 20""",
                (session_id, fts_query)
            ).fetchall()
            fts_results = [r["bullet_text"] for r in fts_rows]
            
            if not query_embedding:
                return fts_results[:limit]
                
            # Fetch vectors for hybrid search
            vec_rows = conn.execute(
                "SELECT bullet_text, vector_json FROM session_digest_vectors WHERE session_id=?",
                (session_id,)
            ).fetchall()
            
            vector_results = []
            for r in vec_rows:
                if r["vector_json"]:
                    try:
                        vector_results.append((r["bullet_text"], json.loads(r["vector_json"])))
                    except Exception:
                        pass
                        
            from mechanics.system.memory.vector import hybrid_search
            return hybrid_search(fts_results, vector_results, query_embedding, top_k=limit)
        except Exception as e:
            log.warning(f"Hybrid search failed: {e}")
            return []

def active_recall_search(session_id: int, query_text: str, limit: int = 10) -> list[str]:
    """Execute a deep FTS5 search across all past chapters specifically for resolving player 'recall' questions."""
    # We can just reuse the highly-optimized FTS chapter search, maybe with a higher limit.
    return search_chapter_digests(session_id, query_text, limit=limit)


def format_digest_prompt_block(session_id: int, query_context: str = "", max_recent: int = 6, max_relevant: int = 6, query_embedding: list[float] = None) -> str:
    """Format the chapter digest into a compact prompt block for LLM injection.
    Uses Hybrid Retrieval: chronological recent bullets + semantic relevant bullets via FTS5.
    Bullets are organized into subsections by their [HOOK] and [RESOURCE] tag prefixes.
    """
    bullets = get_chapter_digest(session_id)
    if not bullets:
        return ""
        
    # 1. Grab recent chronological anchor
    recent = bullets[-max_recent:]
    recent_set = set(recent)
    
    # 2. Grab semantically relevant historic bullets
    relevant = []
    if query_context:
        fts_matches = search_chapter_digests(session_id, query_context, limit=max_relevant, query_embedding=query_embedding)
        for match in fts_matches:
            if match not in recent_set:
                relevant.append(match)
                
    if not recent and not relevant:
        return ""

    # 3. Split bullets into subsections by tag prefix
    def _categorize(bullet_list: list[str]) -> tuple[list[str], list[str], list[str]]:
        """Returns (story_events, hooks, resources)."""
        story, hooks, resources = [], [], []
        for b in bullet_list:
            if b.startswith("[HOOK]"):
                hooks.append(b[len("[HOOK]"):].strip())
            elif b.startswith("[RESOURCE]"):
                resources.append(b[len("[RESOURCE]"):].strip())
            else:
                story.append(b)
        return story, hooks, resources

    lines = ["[PAST ARC MEMORY — Earlier events in this adventure]:"]
    
    # If we pulled older relevant bullets, list them first as "Relevant History"
    if relevant:
        rel_story, rel_hooks, rel_resources = _categorize(relevant)
        lines.append("(Relevant History):")
        for b in rel_story:
            lines.append(f"• {b}")
        if rel_hooks:
            for b in rel_hooks:
                lines.append(f"• [Hook] {b}")
        if rel_resources:
            for b in rel_resources:
                lines.append(f"• [Resource] {b}")
            
    # Then append the strict chronological recent anchor, split by category
    if recent:
        rec_story, rec_hooks, rec_resources = _categorize(recent)
        if relevant:
            lines.append("(Recent Arc):")

        if rec_story:
            lines.append("(Story Events):")
            for b in rec_story:
                lines.append(f"• {b}")

        if rec_hooks:
            lines.append("(Active Hooks & Rumors):")
            for b in rec_hooks:
                lines.append(f"• {b}")

        if rec_resources:
            lines.append("(Recent Resource Diffs):")
            for b in rec_resources:
                lines.append(f"• {b}")
            
    # Subsystem 1: Inject Tier 3 Saga Chronicles above Tier 2
    chronicles = get_session_chronicles(session_id)
    if chronicles:
        # Windowing: Only show the last 3 chapters to prevent unbounded token growth
        recent_chronicles = chronicles[-3:]
        chronicle_lines = ["[SAGA CHRONICLES — Epic events of past chapters]:"]
        if len(chronicles) > len(recent_chronicles):
            chronicle_lines.append(f"• [Earlier chapters 1 through {chronicles[-4]['chapter_number']} have been archived from immediate memory]")
        for c in recent_chronicles:
            ch_num = c["chapter_number"]
            act = c["act_title"]
            narr = c["summary_narrative"]
            chronicle_lines.append(f"• Chapter {ch_num} ({act}): {narr}")
        return "\n".join(chronicle_lines) + "\n\n" + "\n".join(lines)
        
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Advanced Memory (Tier 3: Chronicles & Tier 1.5: NPC Episodic Memory)
# ---------------------------------------------------------------------------

def add_session_chronicle(session_id: int, chapter_number: int, act_title: str, summary_narrative: str, consequences: list = None):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO session_chronicles 
               (session_id, chapter_number, act_title, summary_narrative, key_consequences_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (session_id, chapter_number, act_title, summary_narrative, json.dumps(consequences or []), time.time())
        )

def get_session_chronicles(session_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM session_chronicles WHERE session_id=? ORDER BY chapter_number ASC", 
            (session_id,)
        ).fetchall()
        return [dict(r) for r in rows]

def add_npc_memory(session_id: int, npc_name: str, turn_index: int, memory_fact: str, sentiment_delta: int = 0, importance: int = 1, is_secret: bool = False):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO npc_memories 
               (session_id, npc_name, turn_index, memory_fact, sentiment_delta, importance, is_secret, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (session_id, npc_name, turn_index, memory_fact, sentiment_delta, importance, 1 if is_secret else 0, time.time())
        )

def get_npc_memories(session_id: int, npc_name: str) -> list[dict]:
    with get_conn() as conn:
        # Sort by importance (Salience) first, then recency, to prevent core memories from being pushed out
        rows = conn.execute(
            "SELECT * FROM npc_memories WHERE session_id=? AND lower(npc_name)=lower(?) ORDER BY importance DESC, turn_index DESC", 
            (session_id, npc_name)
        ).fetchall()
        return [dict(r) for r in rows]
