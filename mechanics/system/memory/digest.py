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

log = logging.getLogger("hikayat.memory.digest")

# Number of raw turns kept in working memory (was 8, now 4 for tighter Tier-1).
RAW_HISTORY_LIMIT: int = 4

# Minimum raw turns before we bother generating a digest.
MIN_TURNS_FOR_DIGEST: int = 3

# Maximum bullets emitted per standard 4-turn digest window.
MAX_WINDOW_DIGEST_BULLETS: int = 4
MAX_DIGEST_BULLETS: int = MAX_WINDOW_DIGEST_BULLETS

# Digest system prompt — utility-model friendly, enriched with mechanical & recall fields.
_DIGEST_SYSTEM = (
    "You are an archivist for an AI-driven roleplaying game. "
    "Given a list of recent narrative turn summaries, extract the most "
    "important story facts, NPC interactions, player commitments, resource "
    "changes, and unresolved environmental hooks that occurred. "
    "Output strictly JSON with these keys:\n"
    '{"key_events": ["<concise past-tense facts about what happened>"], '
    '"commitments": [{"source_entity": "...", "target_entity": "...", '
    '"commitment_type": "promise|secret|debt|pact|threat", "description": "..."}], '
    '"mechanical_summary": ["<net resource change, e.g. \'Gold: +50 (reward from merchant)\'>"], '
    '"active_hooks": ["<unresolved clue/rumor/environmental detail not yet acted on>"], '
    '"entities": ["<named NPCs involved>"], '
    '"location_tag": "<primary room/location name>", '
    '"quest_ids": ["<active quest_ids touched>"]}'
    "\nRules: mechanical_summary only for EXPLICIT numeric or named resource changes. "
    "active_hooks only for leads the player has NOT yet resolved. "
    "Omit a field if nothing qualifies (use empty list [] or empty string)."
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


def is_arc_boundary_event(session: dict, actions: list, outcome: dict) -> bool:
    """Return True strictly when a narrative arc boundary (travel, dialogue exit, or sub-quest completion) occurred."""
    from mechanics.narrative.intent import is_conversational_exit
    from mechanics.world.mobility import get_session_dialogue_partners

    for a in (actions or []):
        label_lower = str(a.get("label", "")).lower()
        if any(kw in label_lower for kw in _TRAVEL_KEYWORDS):
            return True
        if is_conversational_exit(label_lower) or any(kw in label_lower for kw in _DIALOGUE_EXIT_KEYWORDS):
            if get_session_dialogue_partners(session):
                return True

    for qu in (outcome.get("quest_updates") or []):
        if isinstance(qu, dict) and qu.get("completed_sub_quest_ids"):
            return True

    return False


def should_trigger_digest(session: dict, actions: list, outcome: dict) -> bool:
    """Return True when an arc boundary has been crossed or raw history reached RAW_HISTORY_LIMIT."""
    history = session.get("history") or []
    if len(history) < MIN_TURNS_FOR_DIGEST:
        return False

    if is_arc_boundary_event(session, actions, outcome):
        return True

    if len(history) >= RAW_HISTORY_LIMIT:
        return True

    return False


# ---------------------------------------------------------------------------
# Arc Digest Generator
# ---------------------------------------------------------------------------

def build_deterministic_arc_digest(raw_turns: list) -> dict:
    """Build a complete Tier 2 digest dict (`key_events`, `commitments`,
    `mechanical_summary`, `active_hooks`, `entities`, `location_tag`, `quest_ids`)
    100% deterministically in Python from structured turn history dicts or plain
    turn strings (0 LLM calls, 0 HTTP embedding calls).
    """
    key_events: list[str] = []
    mechanical_summary: list[str] = []
    active_hooks: list[str] = []
    commitments: list[dict] = []
    entities: list[str] = []
    quest_ids: list[str] = []
    location_tag: str = ""

    filtered_turns = [
        t for t in (raw_turns or [])
        if not (isinstance(t, dict) and t.get("type") == "scene")
    ]
    if not filtered_turns:
        return {
            "key_events": [],
            "commitments": [],
            "mechanical_summary": [],
            "active_hooks": [],
            "entities": [],
            "location_tag": "",
            "quest_ids": [],
        }

    has_structured_dicts = any(isinstance(t, dict) for t in filtered_turns)
    if not has_structured_dicts:
        fb = _extractive_fallback([str(t) for t in filtered_turns])
        fb.setdefault("entities", [])
        fb.setdefault("location_tag", "")
        fb.setdefault("quest_ids", [])
        return fb

    def _add_entity(name: str, skip_name: str = "") -> None:
        clean_n = str(name or "").strip()
        if not clean_n or clean_n.lower() in {"none", "player", "hero", skip_name.lower()}:
            return
        if clean_n not in entities:
            entities.append(clean_n)

    for entry in filtered_turns:
        if not isinstance(entry, dict):
            fb = _extractive_fallback([str(entry)])
            for ev in fb.get("key_events", []):
                if ev not in key_events:
                    key_events.append(ev)
            for ms in fb.get("mechanical_summary", []):
                if ms not in mechanical_summary:
                    mechanical_summary.append(ms)
            continue

        char_name = str(entry.get("character_name") or "Player").strip()
        label = str(entry.get("label") or "").strip().rstrip(".")
        loc = str(entry.get("location") or "").strip()
        loc_short = loc.split("➔")[-1].strip() if "➔" in loc else loc
        if loc_short:
            location_tag = loc_short
        nar = str(entry.get("outcome_narrative") or entry.get("narrative") or entry.get("next_narrative") or "").strip()
        first_sent = ""
        if nar:
            m_sent = re.split(r"(?<=[.!?])\s+|(?<=[。！？])\s*", nar, maxsplit=1)
            first_sent = m_sent[0].strip() if m_sent else nar[:180].strip()
            if len(first_sent) > 190:
                first_sent = first_sent[:187].strip() + "…"

        if first_sent:
            loc_prefix = f"At {loc_short}: " if loc_short and loc_short.lower() not in first_sent.lower() else ""
            bullet = f"{loc_prefix}{first_sent}"
            if bullet not in key_events:
                key_events.append(bullet[:200])
        elif label:
            loc_suffix = f" at {loc_short}" if loc_short else ""
            bullet = f"{char_name} performed '{label}'{loc_suffix}."
            if bullet not in key_events:
                key_events.append(bullet[:200])

        for wit in (entry.get("witnessed_by") or []):
            _add_entity(str(wit), skip_name=char_name)
        for npc_item in (entry.get("npcs_present") or []):
            npc_nm = npc_item.get("name") if isinstance(npc_item, dict) else str(npc_item)
            _add_entity(str(npc_nm or ""), skip_name=char_name)

        for raw_c in (entry.get("commitments") or entry.get("new_commitments") or []):
            if isinstance(raw_c, dict) and str(raw_c.get("description") or "").strip():
                commitments.append(raw_c)

        for itm in (entry.get("items_gained") or []):
            if itm:
                r_str = f"Gained: {itm}"
                if r_str not in mechanical_summary:
                    mechanical_summary.append(r_str)

        for co in (entry.get("character_outcomes") or []):
            if not isinstance(co, dict):
                continue
            g_delta = int(co.get("gold_change") or 0)
            if g_delta != 0:
                sign = "+" if g_delta > 0 else ""
                r_str = f"Gold: {sign}{g_delta}"
                if r_str not in mechanical_summary:
                    mechanical_summary.append(r_str)
            for lost_itm in (co.get("items_lost") or []):
                if lost_itm:
                    r_str = f"Lost: {lost_itm}"
                    if r_str not in mechanical_summary:
                        mechanical_summary.append(r_str)

        for ru in (entry.get("relationship_updates") or []):
            if isinstance(ru, dict) and ru.get("npc_name"):
                _add_entity(str(ru["npc_name"]), skip_name=char_name)
                if int(ru.get("delta_score") or 0) != 0:
                    d_val = int(ru["delta_score"])
                    sign = "+" if d_val > 0 else ""
                    r_str = f"Affinity ({ru['npc_name']}): {sign}{d_val}"
                    if r_str not in mechanical_summary:
                        mechanical_summary.append(r_str)

        for qu in (entry.get("quest_updates") or []):
            if not isinstance(qu, dict):
                continue
            q_id = str(qu.get("quest_id") or qu.get("title") or "").strip()
            if q_id and q_id not in quest_ids:
                quest_ids.append(q_id)
            q_status = str(qu.get("status") or "Active")
            q_title = str(qu.get("title") or qu.get("quest_id") or "").strip()
            q_clue = str(qu.get("current_clues") or qu.get("new_clue") or "").strip()
            if q_clue and q_status == "Active":
                h_str = f"{q_title}: {q_clue}" if q_title else q_clue
                if h_str not in active_hooks:
                    active_hooks.append(h_str[:180])

    max_bullets = max(MAX_WINDOW_DIGEST_BULLETS, len(filtered_turns))
    return {
        "key_events": key_events[-max_bullets:],
        "commitments": commitments,
        "mechanical_summary": mechanical_summary[-MAX_WINDOW_DIGEST_BULLETS:],
        "active_hooks": active_hooks[-MAX_WINDOW_DIGEST_BULLETS:],
        "entities": entities,
        "location_tag": location_tag,
        "quest_ids": quest_ids,
    }


def format_digest_bullets_and_commitments(result: dict) -> tuple[list[str], list[dict]]:
    """Convert a digest result dict into tagged bullet strings and commitment records."""
    bullets: list[str] = []
    commitments: list[dict] = []
    if not isinstance(result, dict):
        return bullets, commitments

    raw_bullets = result.get("key_events") or []
    if isinstance(raw_bullets, list):
        cap_events = max(MAX_WINDOW_DIGEST_BULLETS, len(raw_bullets))
        bullets = [str(b).strip() for b in raw_bullets if b and str(b).strip()][:cap_events]

    raw_mech = result.get("mechanical_summary") or []
    if isinstance(raw_mech, list):
        for item in raw_mech[:MAX_WINDOW_DIGEST_BULLETS]:
            text = str(item).strip()
            if text:
                tagged = f"[RESOURCE] {text}" if not text.startswith("[RESOURCE]") else text
                bullets.append(tagged)

    raw_hooks = result.get("active_hooks") or []
    if isinstance(raw_hooks, list):
        for item in raw_hooks[:MAX_WINDOW_DIGEST_BULLETS]:
            text = str(item).strip()
            if text:
                tagged = f"[HOOK] {text}" if not text.startswith("[HOOK]") else text
                bullets.append(tagged)

    raw_commits = result.get("commitments") or []
    if isinstance(raw_commits, list):
        for c in raw_commits:
            if isinstance(c, dict) and c.get("description"):
                commitments.append(c)

    return bullets, commitments


async def generate_arc_digest(
    session_id: int,
    raw_turns: list,
    turn_start: int = 0,
    use_deterministic: bool = True,
) -> tuple[list[str], list[dict]]:
    """Distil ``raw_turns`` into permanent narrative bullets and commitment records.

    Uses `build_deterministic_arc_digest` directly when `use_deterministic=True`
    (0 LLM calls, 0 HTTP embedding calls). Only calls `llm_client.call_llm_json`
    when `use_deterministic=False` is explicitly passed.
    """
    if not raw_turns:
        return [], []

    if use_deterministic:
        result = build_deterministic_arc_digest(raw_turns)
    else:
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
            log.warning("Arc digest LLM call failed (%s); falling back to deterministic summary.", exc)
            result = build_deterministic_arc_digest(raw_turns)
        else:
            if isinstance(result, dict):
                det_meta = build_deterministic_arc_digest(raw_turns)
                merged_ent = list(dict.fromkeys([
                    *(str(e).strip() for e in (result.get("entities") or []) if e and str(e).strip()),
                    *(str(e).strip() for e in (det_meta.get("entities") or []) if e and str(e).strip()),
                ]))
                merged_qids = list(dict.fromkeys([
                    *(str(q).strip() for q in (result.get("quest_ids") or []) if q and str(q).strip()),
                    *(str(q).strip() for q in (det_meta.get("quest_ids") or []) if q and str(q).strip()),
                ]))
                result["entities"] = merged_ent
                if not str(result.get("location_tag") or "").strip():
                    result["location_tag"] = str(det_meta.get("location_tag") or "")
                result["quest_ids"] = merged_qids

    bullets, commitments = format_digest_bullets_and_commitments(result)

    import db as _db

    if bullets:
        try:
            _db.append_chapter_digest(
                session_id=session_id,
                turn_start=turn_start,
                turn_end=turn_start + len(raw_turns) - 1,
                bullets=bullets,
                entities=result.get("entities") if isinstance(result, dict) else None,
                location_tag=str(result.get("location_tag") or "") if isinstance(result, dict) else "",
                quest_ids=result.get("quest_ids") if isinstance(result, dict) else None,
            )
        except Exception as exc:
            log.warning("Failed to persist chapter digest: %s", exc)

    if commitments:
        try:
            turn_number = turn_start + len(raw_turns)
            _db.bulk_add_commitments(session_id, commitments, turn_number=turn_number)
        except Exception as exc:
            log.warning("Failed to persist commitments: %s", exc)

    try:
        _db.run_deterministic_tier3_compaction(session_id)
    except Exception as exc:
        log.warning("Failed to run tier 3 compaction: %s", exc)

    return bullets, commitments


# ---------------------------------------------------------------------------
# Convenience Fire-and-Forget Wrapper
# ---------------------------------------------------------------------------

def fire_digest_if_needed(
    session: dict,
    actions: list,
    outcome: dict,
    history_to_archive: list | None = None,
) -> None:
    """Schedule a digest generation task as a non-blocking asyncio task.

    Passes structured history dicts directly to `generate_arc_digest` so
    `build_deterministic_arc_digest` can extract exact events, resource diffs,
    and hooks with zero LLM calls.
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
                raw_turns=list(turns),
                turn_start=turn_start,
                use_deterministic=True,
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

