"""Cache-ordered prompt assembly.

ORDER = least volatile -> most volatile. Providers reuse the KV cache up to the
first byte that differs, so nothing volatile may appear before something stable.
  Z0a  GM_SHARED_RULES                       (global, all modes)
  Z0b  mode rules + output rules + schema    (global per mode)
  Z1   scenario + style                      (per session)
  Z2   world state + vitals + clock          (per turn)
  Z3   user message                          (per turn)
"""
import functools, hashlib
from typing import Literal

Mode = Literal["narrative", "combat"]
Kind = Literal["turn", "opening"]
SEP = "\n\n"

TURN_OUTPUT_RULES = """TURN OUTPUT REQUIREMENTS:
- `perspective_awareness`: NEVER allow newly arrived NPCs to react to, mention, or intuit recent history events if their name is not in the `[Witnessed by: ...]` tag for that event. They are completely oblivious to what happened before they walked in.
- `entity_audit`: In `present_named_characters`, list EVERY named individual who is physically in the immediate room right now. In `speaking_characters`, list any NPCs who speak aloud in this scene.
- `npcs_present`: MUST include all active friendly/neutral characters present in the room right now. NEVER omit named characters who appear, watch, or speak in your narrative prose.
- `relationship_updates`: When conversing, cooperating, or interacting with eligible peer NPCs (classmates/students in high school drama, allies/contacts in combat genres), output `relationship_updates` with `npc_name`, `delta_score` (+1 to +6 on success/insight, -1 to -6 on offense/fail), and any discovered traits/preferences. In high school scenarios, faculty, parents, and store clerks must NEVER receive relationship updates.
- STRICT TRANSACTION CONSISTENCY: If your narrative prose mentions a specific gold amount gained or spent, an item handed to or found by a character, or a specific damage figure taken - that SAME value MUST appear in `character_outcomes` (gold_change, items_gained, or hp_change respectively). NEVER describe a transaction in prose that you did not also record in character_outcomes. Omissions will be caught and auto-corrected by the engine.
- `next_choices`: Generate 2-5 dynamic, relevant contextual choices reacting strictly to the room, all present NPCs, and active waypoints. If the local puzzle or objective is resolved, do NOT generate redundant micro-checks on the completed obstacle; focus choices on onward travel/departure, talking to present NPCs, or resting. If characters are talking with NPCs, ALWAYS include 1 conversational exit choice (stat: 'NONE', requirement: 0, e.g. 'Excuse yourself and look around the room')."""

QUEST_REQ = {
    "narrative": "- `quest_updates`: For EVERY active quest listed under PRIMARY STORY QUEST / SECONDARY SIDE BOUNTIES, include one entry. Set status=Completed if the objective was achieved, Failed if it failed, or Active if ongoing. Update `objective` and `current_clues` to reflect what happened this turn.",
    "combat":    "- `quest_updates`: Update active quest status if relevant. Do NOT output clues during combat.",
}

@functools.cache
def build_static_core(mode: Mode, kind: Kind) -> str:
    """Z0a + Z0b. Pure function of constants, so it is byte-identical in every process."""
    from llm_client import GM_SHARED_RULES                       # lazy: avoids import cycles
    from game_engine.prompts import SYSTEM_PROMPT
    from game_engine.schemas import OUTCOME_SCHEMA, SCENE_SCHEMA
    from mechanics.combat.core import COMBAT_SYSTEM_PROMPT, COMBAT_CHOICE_SCHEMA
    import json
    mode_block = COMBAT_SYSTEM_PROMPT if mode == "combat" else SYSTEM_PROMPT
    if kind == "turn":
        schema = json.dumps(COMBAT_CHOICE_SCHEMA) if mode == "combat" else OUTCOME_SCHEMA
        tail = [TURN_OUTPUT_RULES, QUEST_REQ[mode]]
    else:
        schema = json.dumps(COMBAT_CHOICE_SCHEMA) if mode == "combat" else SCENE_SCHEMA
        tail = []
    return SEP.join([GM_SHARED_RULES, mode_block, *tail, f"OUTPUT SCHEMA (respond with JSON matching this):\n{schema}"])

def build_session_zone(session: dict) -> str:
    """Z1: changes only when scenario / style settings change."""
    import game_engine
    from game_engine.turn.generation import get_narrative_requirements
    from mechanics.combat.merchant import merchant_prompt_note
    return SEP.join(p.strip() for p in [
        game_engine._scenario_block(session),
        game_engine._style_block(session),
        "STYLE-BOUND NARRATIVE REQUIREMENTS:\n" + get_narrative_requirements(
            session.get("verbosity", "vivid"), session.get("dialogue_mode", "balanced")),
        merchant_prompt_note(scen_key=session.get("scenario")),
    ] if p and p.strip())

def assemble_system_prompt(*zones: str) -> str:
    return SEP.join(z for z in zones if z)

def zone_fingerprints(*zones: str) -> list[str]:
    """Short hashes logged at DEBUG; shows which zone changed when the cache misses."""
    return [hashlib.md5(z.encode()).hexdigest()[:8] for z in zones]

CLOSING_REMINDER = (
    "Respond with ONE JSON object matching the OUTPUT SCHEMA in the system prompt, obeying the "
    "TURN OUTPUT REQUIREMENTS and the active STYLE & DIALOGUE directives."
)
