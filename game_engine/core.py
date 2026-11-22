from __future__ import annotations
import game_engine
"""
Game engine: turns character/session/lorebook state into LLM prompts, and
turns LLM JSON responses back into state updates. Glue between db.py,
skill_check.py, namegen.py, image_client.py and llm_client.py.
"""

import unicodedata
import logging

from scenario_data import is_nsfw_scenario, uses_nsfw_model  # static-check: ignore[unused-import]

log = logging.getLogger(__name__)







from .keywords import *
from .prompts import *
from .schemas import *

MAX_CAMPAIGN_CHAPTERS = 10


def _get_npc_name(npc) -> str:
    """Safely extracts and strips the name of an NPC from a dict or string without raising AttributeError on None."""
    if not npc:
        return ""
    if isinstance(npc, dict):
        val = npc.get("name") or npc.get("npc_name") or npc.get("character")
        return str(val).strip() if val is not None else ""
    return str(npc).strip()


def _norm_dialogue_name(text: str) -> str:
    if not text:
        return ""
    return unicodedata.normalize('NFKD', str(text)).encode('ASCII', 'ignore').decode('utf-8').strip().lower()


def parse_clue_list(raw_clues) -> list[str]:
    """Unpacks raw clue strings, json arrays, or bullet text into a clean list of strings."""
    if not raw_clues:
        return []
    if isinstance(raw_clues, list):
        return [str(c).strip().lstrip("•-*'\" ") for c in raw_clues if str(c).strip()]
    raw_str = str(raw_clues).strip()
    if not raw_str:
        return []
    if (raw_str.startswith("[") and raw_str.endswith("]")) or (raw_str.startswith("['") or raw_str.startswith("[\"")):
        try:
            import json_repair
            parsed = json_repair.repair_json(raw_str, return_objects=True)
            if isinstance(parsed, list):
                return [str(c).strip().lstrip("•-*'\" ") for c in parsed if str(c).strip()]
        except Exception:
            pass
    lines = []
    for line in raw_str.replace("\\n", "\n").splitlines():
        cleaned = line.strip().lstrip("•-*'\" ").strip()
        if cleaned:
            lines.append(cleaned)
    return lines


def format_concise_bullets(text: str, max_bullets: int = 6) -> str:
    clues = game_engine.parse_clue_list(text)
    if not clues:
        return ""
    return "\n".join(f"• {c}" for c in clues[:max_bullets])
