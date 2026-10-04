import json
import logging
import asyncio

import db
from models.llm_schemas import NarrationOutcome
from llm_client import invoke_llm
from game_engine.context import fetch_and_format_context
import game_engine

log = logging.getLogger(__name__)


NARRATION_SYSTEM_PROMPT = """You are a highly skilled interactive fiction engine (the "Narrator").
Your ONLY job right now is to regenerate the prose (the narrative description of what just happened and what is happening next) and the next available choices.

You MUST NOT change the mechanical outcome of the turn. The facts are absolute and frozen. You are just describing them in vivid, second-person prose according to the player's preferences.

## FROZEN STATE (Authoritative Facts)
The player took the following action(s):
{actions_text}

The engine already resolved the outcome and these are the unchangeable facts:
{frozen_state_text}

## YOUR TASK
1. 'outcome_narrative': Describe the immediate result of the player's action(s). Write exactly what happens based on the frozen mechanics. (e.g. if the mechanics say an attack failed and the player took 5 damage, you describe the player missing and getting hit back).
2. 'next_narrative': Describe the current state of the scene right after the action is resolved. Detail the environment, who is still here, and the immediate atmosphere.
3. 'scene_title': A short 2-5 word title for the current situation.
4. 'next_choices': Propose 2-5 logical, contextual actions the player can take next, given the new situation.

## GUIDELINES
- Respect the verbosity and dialogue preferences.
- If characters died, describe their fall.
- If an item was gained, mention it naturally in the prose.
- Do NOT generate markdown formatting unless it's bold/italics for emphasis. No code blocks.
"""

def _build_frozen_state_text(snapshot: dict) -> str:
    lines = []
    applied = snapshot.get("applied", {})
    
    # Check outcomes
    char_outcomes = applied.get("character_outcomes", [])
    if char_outcomes:
        lines.append("Character Consequences:")
        for co in char_outcomes:
            c_dict = co if isinstance(co, dict) else co.__dict__
            c_name = c_dict.get("name", "Unknown")
            hp_c = c_dict.get("hp_change", 0)
            mp_c = c_dict.get("mp_change", 0)
            status = c_dict.get("status_effects_gained", [])
            lines.append(f" - {c_name}: HP {hp_c}, MP {mp_c}, Status Effects: {status}")
            
    # Location
    loc = applied.get("location")
    if loc:
        lines.append(f"Current Location: {loc}")
        
    # Entities
    npcs = applied.get("npcs_present", [])
    if npcs:
        lines.append(f"NPCs present in the scene: {[n.get('name', '') if isinstance(n, dict) else n for n in npcs]}")
        
    enemies = applied.get("nearby_enemies", [])
    if enemies:
        lines.append(f"Enemies present in the scene: {[e.get('name', '') if isinstance(e, dict) else e for e in enemies]}")
        
    # Loot / XP
    loot = applied.get("items_gained", {})
    if any(loot.values()):
        lines.append(f"Loot gained: {loot}")
        
    xp = applied.get("xp_gained", {})
    if any(xp.values()):
        lines.append(f"XP gained: {xp}")
        
    # Time / Sleep
    t_info = applied.get("time_info", {})
    if t_info:
        lines.append(f"Time advanced. It is now day {t_info.get('day', '?')}, {t_info.get('time', '?')}")
        
    if not lines:
        lines.append("(No significant mechanical changes)")
        
    return "\n".join(lines)


async def run_narration_pass(session: dict, snapshot: dict, attempt: int = 1, stream_callback=None) -> dict:
    """
    Lightweight generation pass that ONLY rewrites narrative and choices,
    treating the provided snapshot's mechanical state as authoritative ground truth.
    """
    session_id = session.get("id", 0)
    
    # 1. Provide context (recent history, lorebook, etc.)
    # We can fetch the context just like standard turn resolution
    context_str = await fetch_and_format_context(session_id, session)
    
    # 2. Build actions text
    actions = snapshot.get("actions", [])
    action_lines = []
    for a in actions:
        tier_label = a.get("check", {}).get("tier_label", "Action")
        action_lines.append(f"[{tier_label}] {a.get('label')}")
    actions_text = "\n".join(action_lines)
    
    # 3. Build frozen state text
    frozen_state_text = _build_frozen_state_text(snapshot)
    
    sys_prompt = NARRATION_SYSTEM_PROMPT.format(
        actions_text=actions_text,
        frozen_state_text=frozen_state_text
    )
    
    user_prompt = f"Context & Lore:\n{context_str}\n\nPlease generate the narration and next choices now based strictly on the frozen mechanics."
    
    # Temperature bump for manual retries (attempt 1 is auto-recovery, attempt 2+ is manual)
    base_temp = 0.7
    if attempt > 1:
        base_temp = min(1.2, base_temp + (attempt - 1) * 0.15)
        
    from llm_client import get_default_model
    model = get_default_model(is_nsfw=session.get("is_nsfw", False))
    
    result = await invoke_llm(
        system_prompt=sys_prompt,
        user_prompt=user_prompt,
        response_format=NarrationOutcome,
        temperature=base_temp,
        model=model,
        stream_callback=stream_callback
    )
    
    # Convert NarrationOutcome to dict
    out = dict(result) if hasattr(result, "keys") else result.model_dump()
    return out
