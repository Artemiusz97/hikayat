from __future__ import annotations
"""
mechanics/memory/digest.py — Episodic Chapter Digest (Tier 2 Memory)
=====================================================================
Converts raw rolling history into compact, permanent narrative bullet-points
that survive the 8-turn (now 4-turn) working-memory window.

Triggers:
  - Zone / establishment travel
  - Dialogue exit with a named NPC
  - Story sub-quest completion
  - Working history reaches RAW_HISTORY_LIMIT (4 raw turns)

The digest uses use_utility=True so it runs on the lightweight LLM_UTILITY_MODEL
when configured.  If not configured, it automatically falls back to the primary
LLM_MODEL — no special setup required.
"""

import asyncio
import json
import logging
import re
from typing import TYPE_CHECKING

import db

log = logging.getLogger("hikayat.memory.digest")

# Number of raw turns kept in working memory (was 8, now 4 for tighter Tier-1).
RAW_HISTORY_LIMIT: int = 4

# Minimum raw turns before we bother generating a digest.
MIN_TURNS_FOR_DIGEST: int = 3

# Maximum bullets the LLM may emit per digest call.
MAX_DIGEST_BULLETS: int = 3

# Digest system prompt — utility-model friendly, enriched with mechanical fields.
_DIGEST_SYSTEM = (
    "You are an archivist for an AI-driven roleplaying game. "
    "Given a list of recent narrative turn summaries, extract the most "
    "important story facts, NPC interactions, player commitments, resource "
    "changes, and unresolved environmental hooks that occurred. "
    "Output strictly JSON with EXACTLY these four keys:\n"
    '{"key_events": ["<2-3 concise past-tense facts about what happened>"], '
    '"commitments": [{"source_entity": "...", "target_entity": "...", '
    '"commitment_type": "promise|secret|debt|pact|threat", "description": "..."}], '
    '"mechanical_summary": ["<net resource change, e.g. \'Gold: +50 (reward from merchant)\', '
    '\'Lost: Iron Key\', \'Spent: 2 Health Potions\'>"], '
    '"active_hooks": ["<unresolved clue/rumor/environmental detail the party has not yet acted on, '
    'e.g. \'Scratching behind the chapel altar — uninvestigated\', '
    '\'Wanted poster seen for a red-cloaked rogue\'>"]}'
    "\nRules: mechanical_summary only for EXPLICIT numeric or named resource changes. "
    "active_hooks only for leads the player has NOT yet resolved. "
    "Omit a field if nothing qualifies (use empty list []). Max 3 items per list."
)


# ---------------------------------------------------------------------------
# Trigger Detection
# ---------------------------------------------------------------------------

_TRAVEL_KEYWORDS = frozenset({
    "travel to", "head to", "depart", "leave the", "walk to", "ride to",
    "move to", "return to", "arrive at", "exit the", "step outside",
    "navigate to", "fly to", "sail to", "teleport to", "warp to",
})

_DIALOGUE_EXIT_KEYWORDS = frozenset({
    "excuse yourself", "step away", "leave conversation",
    "farewell", "say goodbye", "step back", "see you", "part ways",
    "walk away", "end the conversation", "head out",
})


def should_trigger_digest(session: dict, actions: list, outcome: dict) -> bool:
    """Return True when an arc boundary has been crossed and a digest is warranted.

    This is purely synchronous and cheap — just keyword matching against
    action labels and outcome keys so it never adds latency.
    """
    history = session.get("history") or []
    # Must have enough raw turns to be worth summarising
    if len(history) < MIN_TURNS_FOR_DIGEST:
        return False

    from mechanics.narrative.intent import is_conversational_exit
    from mechanics.world.mobility import get_session_dialogue_partners

    for a in (actions or []):
        label_lower = str(a.get("label", "")).lower()
        # Zone/establishment travel
        if any(kw in label_lower for kw in _TRAVEL_KEYWORDS):
            return True
        # Dialogue exit from a named NPC conversation
        if is_conversational_exit(label_lower) or any(kw in label_lower for kw in _DIALOGUE_EXIT_KEYWORDS):
            if get_session_dialogue_partners(session):
                return True

    # Story sub-quest completed this turn
    for qu in (outcome.get("quest_updates") or []):
        if isinstance(qu, dict) and qu.get("completed_sub_quest_ids"):
            return True

    # Working history is at or over the raw window — time to archive
    if len(history) >= RAW_HISTORY_LIMIT:
        return True

    return False


# ---------------------------------------------------------------------------
# Arc Digest Generator
# ---------------------------------------------------------------------------

async def generate_arc_digest(
    session_id: int,
    raw_turns: list[str],
    turn_start: int = 0,
) -> tuple[list[str], list[dict]]:
    """Distil ``raw_turns`` into permanent narrative bullets and commitment records.

    Uses ``use_utility=True`` so the call targets ``LLM_UTILITY_MODEL`` when
    configured; falls back silently to the primary model if not.

    Returns ``(bullets, commitments)`` — both empty lists on any error so the
    caller never needs to handle exceptions from this background task.
    """
    if not raw_turns:
        return [], []

    import llm_client  # lazy import to avoid circular deps at module load time

    turns_text = "\n".join(f"- {t}" for t in raw_turns)
    user_msg = (
        f"Recent adventure turns to archive (oldest first):\n{turns_text}\n\n"
        f"Extract key_events, commitments, mechanical_summary, and active_hooks as JSON."
    )

    try:
        result = await llm_client.call_llm_json(
            system_prompt=_DIGEST_SYSTEM,
            user_prompt=user_msg,
            temperature=0.2,
            max_tokens=600,
            retries=1,
            use_utility=True,
        )
    except Exception as exc:
        # Digest is best-effort; never crash the caller
        log.warning("Arc digest LLM call failed (%s); falling back to extractive summary.", exc)
        result = _extractive_fallback(raw_turns)

    bullets: list[str] = []
    commitments: list[dict] = []

    if isinstance(result, dict):
        # -- key_events: plain narrative bullets (no prefix)
        raw_bullets = result.get("key_events") or []
        if isinstance(raw_bullets, list):
            bullets = [str(b).strip() for b in raw_bullets if b and str(b).strip()][:MAX_DIGEST_BULLETS]

        # -- mechanical_summary: resource diffs tagged [RESOURCE]
        raw_mech = result.get("mechanical_summary") or []
        if isinstance(raw_mech, list):
            for item in raw_mech[:MAX_DIGEST_BULLETS]:
                text = str(item).strip()
                if text:
                    tagged = f"[RESOURCE] {text}" if not text.startswith("[RESOURCE]") else text
                    bullets.append(tagged)

        # -- active_hooks: unresolved leads tagged [HOOK]
        raw_hooks = result.get("active_hooks") or []
        if isinstance(raw_hooks, list):
            for item in raw_hooks[:MAX_DIGEST_BULLETS]:
                text = str(item).strip()
                if text:
                    tagged = f"[HOOK] {text}" if not text.startswith("[HOOK]") else text
                    bullets.append(tagged)

        # -- commitments: structured promise/debt records
        raw_commits = result.get("commitments") or []
        if isinstance(raw_commits, list):
            for c in raw_commits:
                if isinstance(c, dict) and c.get("description"):
                    commitments.append(c)

    # Persist results
    if bullets:
        try:
            import asyncio
            from llm_client import get_embedding
            embeddings = await asyncio.gather(*(get_embedding(b) for b in bullets))
        except Exception as e:
            log.warning(f"Failed to fetch embeddings for digest: {e}")
            embeddings = None

        try:
            db.append_chapter_digest(
                session_id=session_id,
                turn_start=turn_start,
                turn_end=turn_start + len(raw_turns) - 1,
                bullets=bullets,
                embeddings=embeddings,
            )
        except Exception as exc:
            log.warning("Failed to persist chapter digest: %s", exc)

    if commitments:
        try:
            turn_number = turn_start + len(raw_turns)
            db.bulk_add_commitments(session_id, commitments, turn_number=turn_number)
        except Exception as exc:
            log.warning("Failed to persist commitments: %s", exc)

    # Trigger Tier 3 compaction if Tier 2 is getting bloated
    try:
        from mechanics.system.memory.compaction import schedule_tier3_compaction_if_needed
        schedule_tier3_compaction_if_needed(session_id)
    except Exception as exc:
        log.warning("Failed to schedule tier 3 compaction: %s", exc)

    return bullets, commitments


# ---------------------------------------------------------------------------
# Convenience Fire-and-Forget Wrapper
# ---------------------------------------------------------------------------

def fire_digest_if_needed(
    session: dict,
    actions: list,
    outcome: dict,
    history_to_archive: list[str] | None = None,
) -> None:
    """Schedule a digest generation task as a non-blocking asyncio task.

    Intended to be called from synchronous post-turn code inside an already-
    running event loop (e.g. from apply_outcome or a Discord cog callback).
    Silently skips if no event loop is running.
    """
    session_id = session.get("id")
    if not session_id:
        return

    if not should_trigger_digest(session, actions, outcome):
        return

    turns = history_to_archive or (session.get("history") or [])
    if not turns:
        return

    turn_start = max(0, len(session.get("history") or []) - len(turns))

    async def _run():
        try:
            await generate_arc_digest(
                session_id=session_id,
                raw_turns=[str(t) for t in turns],
                turn_start=turn_start,
            )
        except Exception as exc:
            log.warning("Background arc digest task failed: %s", exc)

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(_run())
    except RuntimeError:
        pass  # no event loop — fine, digest is optional


# ---------------------------------------------------------------------------
# Pure-code extractive fallback (zero LLM cost)
# ---------------------------------------------------------------------------

_CHECK_RE = re.compile(r"\[([^\]]+)\]")
# Fallback resource patterns (deliberately simple — LLM path is the rich version)
_FB_GOLD_RE = re.compile(r'(\d+)\s+(?:gold|coins?|credits?)', re.I)
_FB_ITEM_RE = re.compile(r'(?:gained?|found?|received?|picked up)\s+(?:a|an|the)?\s*([A-Z][a-zA-Z\s]{3,25})', re.I)


def _extractive_fallback(raw_turns: list[str]) -> dict:
    """Produce a minimal digest dict purely from string extraction when the
    LLM digest call fails.  Extracts check tier labels and NPC names to
    create terse factual bullet strings, and scans for gold/item mentions
    to produce basic [RESOURCE] bullets.
    """
    bullets = []
    resource_bullets = []

    for t in raw_turns[-MAX_DIGEST_BULLETS:]:
        text = str(t).strip()
        # Truncate to a sensible length
        if len(text) > 200:
            cut = text[:200]
            last = max(cut.rfind("."), cut.rfind("!"), cut.rfind("?"))
            text = cut[:last + 1].strip() if last > 80 else cut.strip() + "…"
        if text:
            bullets.append(text)

        # Extract resource hints from the full raw turn text
        full = str(t)
        gold_match = _FB_GOLD_RE.search(full)
        if gold_match:
            resource_bullets.append(f"[RESOURCE] ~{gold_match.group(1)} gold involved")
        item_match = _FB_ITEM_RE.search(full)
        if item_match:
            resource_bullets.append(f"[RESOURCE] Gained: {item_match.group(1).strip().title()}")

    # Deduplicate resource bullets
    seen = set()
    deduped = []
    for r in resource_bullets:
        if r not in seen:
            seen.add(r)
            deduped.append(r)

    return {
        "key_events": bullets,
        "commitments": [],
        "mechanical_summary": deduped[:MAX_DIGEST_BULLETS],
        "active_hooks": [],
    }

