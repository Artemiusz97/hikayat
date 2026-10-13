"""Cache-ordered prompt assembly.

ORDER = least volatile -> most volatile. Providers reuse the KV cache up to the
first byte that differs, so nothing volatile may appear before something stable.
  Z0a  GM_SHARED_RULES                       (global, all modes)
  Z0b  mode rules + output rules + schema    (global per mode)
  Z1   scenario + style                      (per session)
  Z1b  world canon: places, factions, rules  (changes only when the lorebook/roster changes)
  Z2   sheets + scene context + clock        (per turn; clock is always last)
  Z3   user message: quests, waypoints, caseboard, history, actions (per turn)
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
- STRICT PHYSICAL PRESENCE ISOLATION: Characters listed under 'Contacts elsewhere in the world (NOT present in this scene)' or any characters stationed in other locations MUST NOT physically appear, perform actions, stand nearby, react, or be in the immediate room. NEVER write sentences depicting an absent character standing, watching, holding items, or speaking in the scene unless the player explicitly travels to them or summons them. Spoken in-character dialogue referring to or asking about an absent person is allowed, but their physical presence or direct action is strictly prohibited.
- `relationship_updates`: When conversing, cooperating, or interacting with eligible peer NPCs (classmates/students in high school drama, allies/contacts in combat genres), output `relationship_updates` with `npc_name`, `delta_score` (+1 to +6 on success/insight, -1 to -6 on offense/fail), and any discovered traits/preferences. In high school scenarios, faculty, parents, and store clerks must NEVER receive relationship updates.
- STRICT TRANSACTION CONSISTENCY: If your narrative prose mentions a specific gold amount gained or spent, an item handed to or found by a character, or a specific damage figure taken - that SAME value MUST appear in `character_outcomes` (gold_change, items_gained, or hp_change respectively). NEVER describe a transaction in prose that you did not also record in character_outcomes. Omissions will be caught and auto-corrected by the engine.
- ITEM POSSESSION GROUNDING: Personal items, snacks, food, drinks, and belongings held by or associated with NPCs remain strictly NPC property and cannot transfer to the player without an explicit narrative handoff. In `next_choices`, NEVER generate choices offering, giving, or sharing an item ('your [item]', 'half your [item]') unless that item is explicitly in the player's carried inventory. If an NPC holds or eats an item/prop, choices may only comment on or ask about their item.
- `next_choices`: Generate 2-5 dynamic, relevant contextual choices reacting strictly to the room, all present NPCs, and active waypoints. In active dialogue, every conversational choice MUST require a skill check (DC 5-8 with appropriate stat: CHA, INT, PER, AGI), EXCEPT the 1 dedicated conversational exit choice (stat: 'NONE', requirement: 0, e.g. 'Excuse yourself and look around the room'). In free exploration, quest-related actions MUST require a skill check (DC 5-8); only routine non-quest exploration (starting dialogue, travel, inspecting props, observing surroundings, sleep, merchants, notice boards) are Free Actions (stat: 'NONE', requirement: 0). If the local puzzle or objective is resolved, do NOT generate redundant micro-checks on the completed obstacle; focus choices on onward travel/departure, talking to present NPCs, or resting."""

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

def build_language_directive(session: dict) -> str:
    lang = (session.get("narration_language") or session.get("language") or "en").lower().strip()
    if lang == "pl":
        lead_gender = (session.get("lead_character_gender") or session.get("gender") or "male").lower()
        is_female = any(kw in lead_gender for kw in ("fem", "woman", "girl", "lady", "she"))
        gender_inflection = (
            "The protagonist is FEMALE. Use feminine verb endings and adjectives when describing them "
            "(e.g., 'zrobiłaś', 'poszłaś', 'zauważyłaś', 'byłaś gotowa')."
            if is_female else
            "The protagonist is MALE. Use masculine verb endings and adjectives when describing them "
            "(e.g., 'zrobiłeś', 'poszedłeś', 'zauważyłeś', 'byłeś gotowy')."
        )
        return (
            "LANGUAGE DIRECTIVE: POLISH (Język polski)\n"
            "- Output `outcome_narrative`, `next_narrative`, `scene_title`, and all `next_choices.label` strictly in natural, immersive Polish.\n"
            f"- GRAMMATICAL GENDER: {gender_inflection}\n"
            "- CRITICAL SCHEMA RULE: Keep all JSON keys (e.g. 'outcome_narrative', 'next_choices'), stat abbreviations (STR, PER, END, CHA, INT, AGI, LUK, NONE), and status effect codes strictly in English.\n"
            "- Procedural items, weapon descriptors, and NPC titles must be in natural Polish (e.g. 'Żelazny miecz', 'Karczmarz', 'Mikstura leczenia'). Keep proper character names and place names intact."
        )
    elif lang == "ms":
        return (
            "LANGUAGE DIRECTIVE: MALAY (Bahasa Melayu)\n"
            "- Output `outcome_narrative`, `next_narrative`, `scene_title`, and all `next_choices.label` strictly in evocative, natural Bahasa Melayu.\n"
            "- Use natural literary fantasy storytelling ('kamu' or 'anda' adapted to narrative tone and dramatic tension).\n"
            "- CRITICAL SCHEMA RULE: Keep all JSON keys, stat abbreviations (STR, PER, END, CHA, INT, AGI, LUK, NONE), and status effect codes strictly in English.\n"
            "- Procedural items, weapon descriptors, and NPC titles must be in natural Malay (e.g. 'Pedang Besi', 'Pemilik Kedai', 'Penawar Luka'). Keep proper character names and place names intact."
        )
    return ""

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
        build_language_directive(session),
    ] if p and p.strip())

#: Fixed size cap for Z1b. Deliberately NOT tied to DynamicTokenBudget's scene mode:
#: a mode switch (combat <-> exploration) must never change these bytes.
WORLD_CANON_MAX_CHARS = 2400
WORLD_CANON_HEADER = "KNOWN WORLD - CANON (stable reference: established places, factions & canon rules):"
SCENE_CONTEXT_HEADER = "KNOWN WORLD - CURRENT SCENE (location, people present, live standings):"

def _cap(text: str, limit: int) -> str:
    """Deterministic tail cut at the last line / list boundary before `limit`."""
    if len(text) <= limit:
        return text
    cut = text[:limit]
    boundary = max(cut.rfind("\n"), cut.rfind("; "))
    return (cut[:boundary] if boundary > limit // 2 else cut).rstrip(" ;\n") + " …"

def build_world_canon_zone(session: dict, world: dict | None = None) -> str:
    """Z1b: slow-changing world facts. Same bytes turn after turn until the lorebook changes."""
    import game_engine
    text = game_engine._world_canon_text(session["id"], world=world)
    return f"{WORLD_CANON_HEADER}\n{_cap(text, WORLD_CANON_MAX_CHARS)}" if text.strip() else ""

def assemble_system_prompt(*zones: str) -> str:
    return SEP.join(z for z in zones if z)

def zone_fingerprints(*zones: str) -> list[str]:
    """Short hashes logged at DEBUG; shows which zone changed when the cache misses."""
    return [hashlib.md5(z.encode()).hexdigest()[:8] for z in zones]

CLOSING_REMINDER = (
    "Respond with ONE JSON object matching the OUTPUT SCHEMA in the system prompt, obeying the "
    "TURN OUTPUT REQUIREMENTS and the active STYLE & DIALOGUE directives."
)
