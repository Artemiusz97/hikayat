from __future__ import annotations
import json
import logging

log = logging.getLogger("hikayat.memory.compaction")

SAGA_CHRONICLE_SCHEMA = """{
  "act_title": "string, a 2-4 word dramatic title for this set of events (e.g. 'The Fall of Oakhaven' or 'Betrayal at the Docks')",
  "summary_narrative": "string, a cohesive 3-sentence summary of the provided narrative bullets, describing the macro-plot progression without getting bogged down in minor tactical details",
  "key_consequences": ["string, 1-2 major permanent outcomes from this arc (e.g. 'The Rebel Alliance is broken' or 'Kael acquired the Sun Blade')"]
}"""

SAGA_SYSTEM_PROMPT = """You are the Grand Chronicler of a long-running tabletop RPG campaign.
Your task is to take a raw list of episodic chapter bullets and distill them into a single high-level Tier 3 Saga Chronicle.
Focus only on major plot points, key character relationships, and lasting consequences. Discard minor combat encounters or trivial loot.

Return ONLY valid JSON matching this schema:
""" + SAGA_CHRONICLE_SCHEMA

# In-memory lock to prevent race conditions from concurrent turn resolutions
_active_compactions: set[int] = set()

def build_deterministic_chronicle(bullets_to_compact: list[str], chapter_number: int = 1) -> dict:
    """Deterministic Tier 3 Saga Chronicle builder (0 LLM calls)."""
    events = [b for b in bullets_to_compact if not b.startswith(("[RESOURCE]", "[HOOK]"))]
    resources = [b.replace("[RESOURCE]", "").strip() for b in bullets_to_compact if b.startswith("[RESOURCE]")]
    summary_parts = events[:3] if events else [b[:150] for b in bullets_to_compact[:3]]
    summary_narrative = " ".join(summary_parts)
    key_consequences = resources[:2] if resources else (events[-2:] if len(events) >= 2 else events[:1])
    return {
        "act_title": f"Chronicle of Chapter {chapter_number}",
        "summary_narrative": summary_narrative,
        "key_consequences": key_consequences,
    }


def run_deterministic_tier3_compaction(session_id: int) -> bool:
    """Compatibility wrapper delegating persistence orchestration to Layer 3 (`db.run_deterministic_tier3_compaction`)."""
    import db as _db
    return _db.run_deterministic_tier3_compaction(session_id)


async def _run_tier3_compaction(session_id: int, use_deterministic: bool = True):
    import db as _db

    if use_deterministic:
        _db.run_deterministic_tier3_compaction(session_id)
        return

    if session_id in _active_compactions:
        return

    _active_compactions.add(session_id)
    try:
        bullets = _db.get_chapter_digest(session_id)
        if len(bullets) < 24:
            return

        bullets_to_compact = bullets[:15]
        existing = _db.get_session_chronicles(session_id)
        chapter_number = len(existing) + 1

        bullet_text = "\n".join(f"- {b}" for b in bullets_to_compact)
        prompt = f"Distill the following arc bullets into a Chronicle summary:\n\n{bullet_text}"
        try:
            import llm_client as _llm_client
            from game_engine.prompt_layout import build_side_channel_language_directive
            raw_result = await _llm_client.call_llm_json(
                system_prompt=(
                    f"{SAGA_SYSTEM_PROMPT}\n\n{_saga_dir}"
                    if (_saga_dir := build_side_channel_language_directive(
                        _db.get_session(session_id) or {},
                        text_fields=("act_title", "summary_narrative", "key_consequences"),
                        style="narrative",
                    ))
                    else SAGA_SYSTEM_PROMPT
                ),
                user_prompt=prompt,
                temperature=0.2,
                max_tokens=600,
                retries=1,
                use_utility=True,
            )
            result = json.loads(raw_result) if isinstance(raw_result, str) else (raw_result if isinstance(raw_result, dict) else {})
        except Exception:
            result = build_deterministic_chronicle(bullets_to_compact, chapter_number=chapter_number)

        act_title = result.get("act_title", f"Chronicle of Chapter {chapter_number}")
        summary_narrative = result.get("summary_narrative", "")
        key_consequences = result.get("key_consequences", [])

        if summary_narrative:
            existing = _db.get_session_chronicles(session_id)
            chapter_number = len(existing) + 1

            _db.add_session_chronicle(
                session_id=session_id,
                chapter_number=chapter_number,
                act_title=act_title,
                summary_narrative=summary_narrative,
                consequences=key_consequences,
            )

            _db.remove_oldest_chapter_digest_bullets(session_id, len(bullets_to_compact))

            log.info(f"Successfully compacted {len(bullets_to_compact)} bullets into Saga Chronicle Chapter {chapter_number}: {act_title}")
    except Exception as exc:
        log.error(f"Failed to run Tier 3 Saga Compaction: {exc}")
    finally:
        _active_compactions.discard(session_id)


def schedule_tier3_compaction_if_needed(session_id: int):
    """Run deterministic compaction synchronously when Tier 2 digest reaches threshold."""
    import db as _db
    bullets = _db.get_chapter_digest(session_id)
    if len(bullets) >= 24:
        _db.run_deterministic_tier3_compaction(session_id)
