import game_engine
"""
Game engine: turns character/session/lorebook state into LLM prompts, and
turns LLM JSON responses back into state updates. Glue between db.py,
skill_check.py, namegen.py, image_client.py and llm_client.py.
"""

import json
import random
import re
import time
import unicodedata
import db
import logging
import namegen
import scenario_data

from config import ENABLE_DYNAMIC_MULTIPASS, LLM_PASS1_TIMEOUT, LLM_PASS2_TIMEOUT
from scenario_data import is_nsfw_scenario
from character_data import STAT_EFFECTS, STAT_NAMES, inventory_capacity, sanitize_status_effects
from llm_client import call_llm_json

log = logging.getLogger(__name__)

from mechanics.combat.merchant import (
    merchant_prompt_note,
    generate_merchant_shop,
    evaluate_items_for_sale,
)

from mechanics.social.relationships import (
    format_llm_relationship_context,
    get_relationship_modifier,
    get_relationship_tier
)

from mechanics.social.factions import (
    format_llm_faction_context, format_llm_player_faction_block,
    get_npc_affiliation_chance, guess_hierarchy_template,
    generate_procedural_leadership_roster, get_rank_title, get_eligible_rank,
    promote_player_in_roster, remove_player_from_roster, get_faction_tier,
)

from mechanics.social.races import normalize_race, format_race_display, get_scenario_race_hint
from mechanics.social.persona import normalize_appearance, format_persona_summary

from mechanics.world.locations import (
    is_location_engine_enabled,
    format_llm_location_context,
    process_llm_location_update,
    reconcile_movement_location,
    extract_movement_destination,
    is_movement_action,
    is_hub_location,
    is_interzone_travel,
    format_transit_location_string,
    is_transit_location,
    is_school_scenario,
    parse_tiered_location,
    format_tiered_location_string,
    get_primary_location_name,
    get_zone_location_name,
)

from skill_check import CheckResult

from .keywords import *
from .prompts import *
from .schemas import *
from mechanics.narrative.bounty import BOUNTY_BOARD_SCHEMA, BOUNTY_BOARD_SYSTEM_PROMPT, generate_bounty_board

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
