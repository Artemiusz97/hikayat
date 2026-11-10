from __future__ import annotations
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
- STRICT PHYSICAL PRESENCE ISOLATION: Characters listed under 'Contacts elsewhere in the world (NOT present in this scene)' or any characters stationed in other locations MUST NOT physically appear, perform actions, stand nearby, react, or be in the immediate room. NEVER write sentences depicting an absent character standing, watching, holding items, or speaking in the scene unless the player explicitly travels to them or summons them. Spoken in-character dialogue referring to or asking about an absent person is allowed, but their physical presence or direct action is strictly prohibited.
- PRE-TURN MECHANICAL AUTHORITY: All HP, MP, Gold, Inventory, Relationship Affinity, Location, and Quest Stage updates have ALREADY been resolved deterministically by the engine in the `[PRE-TURN ...]` directives. Narrate those exact outcomes faithfully without inventing contradictory transactions.
- ITEM POSSESSION GROUNDING: Personal items, snacks, food, drinks, and belongings held by or associated with NPCs remain strictly NPC property and cannot transfer to the player without an explicit narrative handoff. In `next_choices`, NEVER generate choices offering, giving, or sharing an item ('your [item]', 'half your [item]') unless that item is explicitly in the player's carried inventory. If an NPC holds or eats an item/prop, choices may only comment on or ask about their item.
- `actor_poses`: Optionally update cosmetic `posture` and `holding` for characters whose physical stance or held prop changed during the prose.
- `episodic_memory`: Output a 1-sentence memory fact if a meaningful promise, personal disclosure, or emotional moment occurred with a present NPC this turn; otherwise set to null.
- `cast_events`: Optional list of narrative-suggested cast events: [{"type": "arrive"|"depart"|"engage", "npc": "Exact Name", "reason": "reason", "gender": "male|female (arrive only)", "descriptor": "short physical descriptor (arrive only)"}]. 'arrive' suggests a character entering; 'depart' suggests an NPC saying goodbye and leaving; 'engage' suggests an NPC walking up to speak to player. Python validates each event against location schedules. CAST CONTRACT: Only characters listed in the STAGE PLAN are present. If your prose shows ANY other person physically acting or speaking on-screen (including someone remembered from RECENT HISTORY), you MUST emit an `arrive` event for them with a personal name (invent one for an unnamed person), `gender`, and `descriptor`, and use that name in the prose; otherwise do not depict them.
- PROTAGONIST TITLE EXCLUSIVITY: Refer to the protagonist only as "you" or by name, never by their class/role title, and never describe an NPC using the protagonist's own class/role title.
- NO PHANTOM COMBAT WHEN NEARBY_ENEMIES IS EMPTY: When `Enemies currently present` / `nearby_enemies` is empty (`None`), do NOT narrate active physical combat, monsters/entities lunging to attack, or weapon clashes unless an active `[ANOMALOUS CONTAINMENT OUTCOME DIRECTIVE]` or `[STAGE DIRECTION]` explicitly initiates combat this turn. You may depict atmospheric anomalies, spatial distortion, or forensic clues, but physical combat only occurs when hostile enemies are present in the scene state.
- `next_choices`: In non-combat turns, generate dynamic, contextual roleplay or exploration choices reacting strictly to the room and present NPCs. If an action steps away, leaves, or concludes dialogue, set `"ends_dialogue": true`. In active dialogue, every conversational choice MUST require a skill check across all 7 SPECIAL stats (`STR`, `PER`, `END`, `CHA`, `INT`, `AGI`, `LUK`; `requirement` 3-12), EXCEPT the 1 dedicated conversational exit choice (`stat: "NONE"`, `requirement: 0`). When `[PRE-TURN SOCIAL SEEDS]` is provided, author natural scene-grounded `label` lines for those seeds and copy each seed's exact `topic_id` and `category` onto its `next_choices` entry—NEVER put raw stat names, DC numbers, or spoiler hints inside `label` or narrative prose. In free exploration, quest-related actions MUST require a skill check (DC 4-10); only routine non-quest exploration (starting dialogue, travel, inspecting props, observing surroundings, sleep, merchants, notice boards) are Free Actions (`stat: "NONE"`, `requirement: 0`)."""

QUEST_REQ = {
    "narrative": "",
    "combat":    "",
}

@functools.cache
def build_static_core(mode: Mode, kind: Kind) -> str:
    """Z0a + Z0b. Pure function of constants, so it is byte-identical in every process."""
    from llm_client import GM_SHARED_RULES                       # lazy: avoids import cycles
    from game_engine.prompts import SYSTEM_PROMPT
    from game_engine.schemas import OUTCOME_SCHEMA, COMBAT_OUTCOME_SCHEMA, SCENE_SCHEMA
    from mechanics.combat.core import COMBAT_SYSTEM_PROMPT, COMBAT_CHOICE_SCHEMA
    import json
    mode_block = COMBAT_SYSTEM_PROMPT if mode == "combat" else SYSTEM_PROMPT
    if kind == "turn":
        schema = COMBAT_OUTCOME_SCHEMA if mode == "combat" else OUTCOME_SCHEMA
        tail = [TURN_OUTPUT_RULES]
    else:
        schema = json.dumps(COMBAT_CHOICE_SCHEMA) if mode == "combat" else SCENE_SCHEMA
        tail = []
    return SEP.join([GM_SHARED_RULES, mode_block, *tail, f"OUTPUT SCHEMA (respond with JSON matching this):\n{schema}"])

def _is_female_gender(raw_gender: str | None) -> bool:
    val = str(raw_gender or "").lower().strip()
    return any(kw in val for kw in ("fem", "woman", "girl", "lady", "she", "kobieta", "perempuan", "wanita"))


def build_language_directive(session: dict, kind: Kind = "turn") -> str:
    lang = str(session.get("narration_language") or session.get("language") or "en").lower().strip().split("-")[0]
    is_opening = kind == "opening"
    fields_clause = (
        "`narrative`, `scene_title`, and all `choices.label`"
        if is_opening else
        "`outcome_narrative`, `next_narrative`, `scene_title`, and all `next_choices.label`"
    )
    if lang == "pl":
        lead_gender = session.get("lead_character_gender") or session.get("gender") or "male"
        is_female = _is_female_gender(lead_gender)
        gender_inflection = (
            "The protagonist is FEMALE. Use feminine verb endings and adjectives when describing them "
            "(e.g., 'zrobiłaś', 'poszłaś', 'zauważyłaś', 'byłaś gotowa')."
            if is_female else
            "The protagonist is MALE. Use masculine verb endings and adjectives when describing them "
            "(e.g., 'zrobiłeś', 'poszedłeś', 'zauważyłeś', 'byłeś gotowy')."
        )
        pl_key_examples = "'narrative', 'choices'" if is_opening else "'outcome_narrative', 'next_choices'"
        return (
            "LANGUAGE DIRECTIVE: POLISH (Język polski)\n"
            f"- Output {fields_clause} strictly in natural, immersive Polish.\n"
            f"- GRAMMATICAL GENDER: {gender_inflection}\n"
            f"- CRITICAL SCHEMA RULE: Keep all JSON keys (e.g. {pl_key_examples}), stat abbreviations (STR, PER, END, CHA, INT, AGI, LUK, NONE), and status effect codes strictly in English.\n"
            "- Procedural items, weapon descriptors, and NPC titles must be in natural Polish (e.g. 'Żelazny miecz', 'Karczmarz', 'Mikstura leczenia'). Keep proper character names and place names intact."
        )
    elif lang == "ms":
        return (
            "LANGUAGE DIRECTIVE: MALAY (Bahasa Melayu)\n"
            f"- Output {fields_clause} strictly in evocative, natural Bahasa Melayu.\n"
            "- Use natural literary fantasy storytelling ('kamu' or 'anda' adapted to narrative tone and dramatic tension).\n"
            "- CRITICAL SCHEMA RULE: Keep all JSON keys, stat abbreviations (STR, PER, END, CHA, INT, AGI, LUK, NONE), and status effect codes strictly in English.\n"
            "- Procedural items, weapon descriptors, and NPC titles must be in natural Malay (e.g. 'Pedang Besi', 'Pemilik Kedai', 'Penawar Luka'). Keep proper character names and place names intact."
        )
    elif lang == "zh":
        return (
            "LANGUAGE DIRECTIVE: CHINESE MANDARIN (中文 / 简体中文)\n"
            f"- Output {fields_clause} strictly in natural, evocative Simplified Chinese.\n"
            "- Use natural literary fantasy storytelling with second-person perspective ('你' for the protagonist).\n"
            "- CRITICAL SCHEMA RULE: Keep all JSON keys, stat abbreviations (STR, PER, END, CHA, INT, AGI, LUK, NONE), and status effect codes strictly in English.\n"
            "- Procedural items, weapon descriptors, and NPC titles must be in natural Chinese (e.g. '铁剑', '客栈掌柜', '治疗药水'). Keep proper character names and place names intact."
        )
    elif lang == "de":
        return (
            "LANGUAGE DIRECTIVE: GERMAN (Deutsch)\n"
            f"- Output {fields_clause} strictly in natural, immersive German.\n"
            "- Use standard literary RPG second-person narration ('du' for the protagonist).\n"
            "- CRITICAL SCHEMA RULE: Keep all JSON keys, stat abbreviations (STR, PER, END, CHA, INT, AGI, LUK, NONE), and status effect codes strictly in English.\n"
            "- Procedural items, weapon descriptors, and NPC titles must be in natural German (e.g. 'Eisenschwert', 'Wirt', 'Heiltrank'). Keep proper character names and place names intact."
        )
    return ""


def build_side_channel_language_directive(
    session: dict | None,
    *,
    text_fields: tuple[str, ...] = (),
    preserve_fields: tuple[str, ...] = (),
    style: Literal["narrative", "sms"] = "narrative",
    speaker_gender: str | None = None,
    recipient_gender: str | None = None,
) -> str:
    """Builds a compact language & schema-preservation directive for side-channel LLM subsystems."""
    if not session or not isinstance(session, dict):
        return ""
    lang = str(session.get("narration_language") or session.get("language") or "en").lower().strip().split("-")[0]
    if lang not in ("pl", "ms", "zh", "de"):
        return ""

    fields_target = (
        ", ".join(f"`{f}`" for f in text_fields)
        if text_fields
        else "all player-facing prose/text values"
    )
    preserve_note = (
        "Keep all JSON keys, proper character names, and canonical location paths (`Zone -> Primary Place`) strictly in English/canonical form."
    )
    if preserve_fields:
        preserve_list = ", ".join(f"`{f}`" for f in preserve_fields)
        preserve_note += f" Keep {preserve_list} strictly in canonical English / exact provided strings (do NOT translate them)."

    if lang == "pl":
        if style == "sms":
            gender_parts: list[str] = []
            if speaker_gender:
                spk_f = _is_female_gender(speaker_gender)
                gender_parts.append(
                    "Speaker ('ja') is FEMALE — use feminine 1st-person verb/adjective endings (e.g. 'byłam', 'zrobiłam')."
                    if spk_f else
                    "Speaker ('ja') is MALE — use masculine 1st-person verb/adjective endings (e.g. 'byłem', 'zrobiłem')."
                )
            eff_recip = recipient_gender or session.get("lead_character_gender") or session.get("gender")
            if eff_recip:
                rec_f = _is_female_gender(eff_recip)
                gender_parts.append(
                    "Recipient ('ty') is FEMALE — use feminine 2nd-person endings (e.g. 'byłaś', 'widziałaś')."
                    if rec_f else
                    "Recipient ('ty') is MALE — use masculine 2nd-person endings (e.g. 'byłeś', 'widziałeś')."
                )
            gender_line = (
                f"- GRAMMATICAL GENDER: {' '.join(gender_parts)}\n"
                if gender_parts else ""
            )
            register_line = (
                "- Use natural, everyday Polish mobile texting / social timeline phrasing (casual 'ty' form, natural colloquialisms, zero stiff bookish prose).\n"
            )
        else:
            lead_gender = session.get("lead_character_gender") or session.get("gender") or (session.get("character") or {}).get("gender") or "male"
            is_female = _is_female_gender(lead_gender)
            gender_line = (
                "- GRAMMATICAL GENDER: The protagonist is FEMALE (use feminine Polish endings when addressing/describing them, e.g. 'zrobiłaś', 'gotowa').\n"
                if is_female else
                "- GRAMMATICAL GENDER: The protagonist is MALE (use masculine Polish endings when addressing/describing them, e.g. 'zrobiłeś', 'gotowy').\n"
            )
            register_line = "- Use natural, evocative Polish RPG prose.\n"
        return (
            "LANGUAGE DIRECTIVE: POLISH (Język polski)\n"
            f"- Output {fields_target} strictly in natural, idiomatic Polish.\n"
            f"{register_line}"
            f"{gender_line}"
            f"- CRITICAL SCHEMA RULE: {preserve_note}"
        )

    if lang == "ms":
        register_line = (
            "- Use natural, conversational Bahasa Melayu mobile texting / social media register (relaxed everyday phrasing such as 'awak'/'kau'/'saya' suited to closeness, natural particles like 'lah'/'kan' when casual — avoid stiff formal textbook prose or unprompted English switching).\n"
            if style == "sms" else
            "- Use evocative, natural Bahasa Melayu RPG prose ('kamu' or 'anda' adapted to tone and setting, clear modern literary phrasing).\n"
        )
        return (
            "LANGUAGE DIRECTIVE: MALAY (Bahasa Melayu)\n"
            f"- Output {fields_target} strictly in natural, idiomatic Bahasa Melayu.\n"
            f"{register_line}"
            f"- CRITICAL SCHEMA RULE: {preserve_note}"
        )

    if lang == "zh":
        register_line = (
            "- Use natural everyday Simplified Chinese mobile chat / social media phrasing.\n"
            if style == "sms" else
            "- Use natural, evocative Simplified Chinese RPG prose ('你' for second-person).\n"
        )
        return (
            "LANGUAGE DIRECTIVE: CHINESE MANDARIN (中文 / 简体中文)\n"
            f"- Output {fields_target} strictly in natural Simplified Chinese.\n"
            f"{register_line}"
            f"- CRITICAL SCHEMA RULE: {preserve_note}"
        )

    # lang == "de"
    register_line = (
        "- Use natural everyday German mobile chat / social media phrasing ('du' form).\n"
        if style == "sms" else
        "- Use natural, immersive German RPG prose ('du' form).\n"
    )
    return (
        "LANGUAGE DIRECTIVE: GERMAN (Deutsch)\n"
        f"- Output {fields_target} strictly in natural, idiomatic German.\n"
        f"{register_line}"
        f"- CRITICAL SCHEMA RULE: {preserve_note}"
    )

def build_anomalous_resonance_directive(session: dict) -> str:
    """Static Z1 genre rule for Awakened Resonance (independent of player stats/pips for KV-cache stability)."""
    import scenario_data
    if not scenario_data.is_anomalous_incursions_scenario(session.get("scenario")):
        return ""
    return (
        "AWAKENED RESONANCE & ELEMENTAL LOCK GROUNDING:\n"
        "- Every Awakened Special Agent (including the protagonist) has a permanently locked Attribute, Combat Archetype, and Ability Medium listed in `[Awakened Resonance: ...]` on their Character Sheet.\n"
        "- Freeform actions aligned with a character's locked Attribute and Medium manifest naturally with sensory flavor and circumstantial synergy.\n"
        "- If the protagonist attempts a freeform anomalous power outside their locked Attribute or Medium (unless channelled through an explicitly equipped Relic), narrate the attempt fizzling—it must fizzle or fail to resonate in-universe.\n"
        "- Awakened agents may also bear additive zero-MP Entity Contracts (`[Entity Contracts — ...]`); weave their subtle physical Contract Tells naturally into sensory prose, and when a Pact invocation or toll occurs, portray the atmospheric anomalous manifestation without quoting raw HP, Credits, percentages, or DC numbers.\n"
        "- Mundane Civilians possess zero mana or resonance abilities. Never leak raw stat numbers, Pip counts, Stability percentages, or bracketed internal tags into narrative prose."
    )

def build_session_zone(session: dict, kind: Kind = "turn") -> str:
    """Z1: changes only when scenario / style settings change."""
    import game_engine
    from game_engine.turn.generation import get_narrative_requirements
    from mechanics.combat.merchant import merchant_prompt_note
    return SEP.join(p.strip() for p in [
        game_engine._scenario_block(session),
        game_engine._style_block(session),
        "STYLE-BOUND NARRATIVE REQUIREMENTS:\n" + get_narrative_requirements(
            session.get("verbosity", "vivid"), session.get("dialogue_mode", "balanced")),
        build_anomalous_resonance_directive(session),
        merchant_prompt_note(scen_key=session.get("scenario")),
        build_language_directive(session, kind=kind),
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
