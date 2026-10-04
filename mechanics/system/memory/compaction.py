import asyncio
import json
import logging
import llm_client
import db
from mechanics.system.memory.digest import MAX_DIGEST_BULLETS

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

async def _run_tier3_compaction(session_id: int):
    if session_id in _active_compactions:
        return
        
    _active_compactions.add(session_id)
    try:
        bullets = db.get_chapter_digest(session_id)
        # Threshold for compaction: e.g., 24 bullets
        if len(bullets) < 24:
            return
            
        # Extract the oldest 15 bullets for compaction
        bullets_to_compact = bullets[:15]
        bullet_text = "\n".join(f"- {b}" for b in bullets_to_compact)
        
        prompt = f"Distill the following arc bullets into a Chronicle summary:\n\n{bullet_text}"
        
        raw_result = await llm_client.call_llm_json(
            system_prompt=SAGA_SYSTEM_PROMPT,
            user_prompt=prompt,
            temperature=0.2,
            max_tokens=600,
            retries=1,
            use_utility=True,
        )
        result = json.loads(raw_result) if isinstance(raw_result, str) else (raw_result if isinstance(raw_result, dict) else {})
        
        act_title = result.get("act_title", "Unknown Arc")
        summary_narrative = result.get("summary_narrative", "")
        key_consequences = result.get("key_consequences", [])
        
        if summary_narrative:
            # Figure out chapter number (just count existing chronicles + 1)
            existing = db.get_session_chronicles(session_id)
            chapter_number = len(existing) + 1
            
            db.add_session_chronicle(
                session_id=session_id,
                chapter_number=chapter_number,
                act_title=act_title,
                summary_narrative=summary_narrative,
                consequences=key_consequences
            )
            
            # Remove the compacted bullets from the active tier 2 digest
            db.remove_oldest_chapter_digest_bullets(session_id, len(bullets_to_compact))
            
            log.info(f"Successfully compacted {len(bullets_to_compact)} bullets into Saga Chronicle Chapter {chapter_number}: {act_title}")
    except Exception as exc:
        log.error(f"Failed to run Tier 3 Saga Compaction: {exc}")
    finally:
        _active_compactions.discard(session_id)


def schedule_tier3_compaction_if_needed(session_id: int):
    """Schedules an async compaction task if the session digest is getting bloated."""
    bullets = db.get_chapter_digest(session_id)
    if len(bullets) >= 24:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(_run_tier3_compaction(session_id))
        except RuntimeError:
            pass  # no event loop running
