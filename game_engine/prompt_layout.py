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
- ITEM POSSESSION GROUNDING: Personal items, snacks, food, drinks, and belongings held by or associated with NPCs remain strictly NPC property and cannot transfer to the player without an explicit narrative handoff. In `@@CHOICES`, NEVER generate choices offering, giving, or sharing an item ('your [item]', 'half your [item]') unless that item is explicitly in the player's carried inventory. If an NPC holds or eats an item/prop, choices may only comment on or ask about their item.
- `@@META` (`pose:` / `actor_poses`): Optionally update cosmetic `posture` and `holding` for characters whose physical stance or held prop changed during the prose.
- `@@META` (`memory:`): Output a 1-sentence memory fact if a meaningful promise, personal disclosure, or emotional moment occurred with a present NPC this turn; otherwise omit or write `none`.
- `@@META` (`cast:`): Optional narrative-suggested cast lines (`arrive|depart|engage | Exact Name | male|female | short descriptor | reason`). CAST CONTRACT: Only characters listed in the STAGE PLAN are present. If your prose shows ANY other person physically acting or speaking on-screen (including someone remembered from RECENT HISTORY), you MUST emit a `cast: arrive | ...` line for them with a personal name, gender, and descriptor; otherwise do not depict them.
- PROTAGONIST TITLE EXCLUSIVITY: Refer to the protagonist only as "you" or by name, never by their class/role title, and never describe an NPC using the protagonist's own class/role title.
- NO PHANTOM COMBAT WHEN NEARBY_ENEMIES IS EMPTY: When `Enemies currently present` / `nearby_enemies` is empty (`None`), do NOT narrate active physical combat, monsters/entities lunging to attack, or weapon clashes unless an active `[ANOMALOUS CONTAINMENT OUTCOME DIRECTIVE]` or `[STAGE DIRECTION]` explicitly initiates combat this turn. You may depict atmospheric anomalies, spatial distortion, or forensic clues, but physical combat only occurs when hostile enemies are present in the scene state."""

NARRATIVE_CHOICE_CRAFT_RULES = """CHOICE CRAFT RULES (`@@CHOICES`):
- Choices MUST react strictly to the character's IMMEDIATE room environment, present NPCs, and current scene state. NEVER output choices that are direct copies or titles of active Sub-Quests or Campaign End Goals.
- FOCUSED DIALOGUE MODE (TALKING TO AN NPC): When in active conversation with an NPC, choices MUST be strictly in-conversation options. In quest/investigation dialogues, use standard skill checks (`CHA`, `INT`, `PER`, `STR`, `END`). In social hangouts, casual meetups, and dates, use skill checks for personal rapport and humor alongside Free choices (`NONE | 0`). ALWAYS include 1 Mandatory Exit Choice (`NONE | 0 | ends_dialogue=true | Thank [NPC], excuse yourself, and step away`). Do NOT generate unrelated room exploration choices while face-to-face in dialogue.
- BOUNTY & COMMISSION DIALOGUE GUARDRAIL: When speaking with a client, target, or contact for an active secondary bounty, the NPC may acknowledge unrelated chatter briefly in-character but MUST steer conversation back to the bounty objective.
- ANTI-DIRECTORY RULE: NEVER generate a repetitive list merely stating 'Speak with [NPC A]', 'Speak with [NPC B]'. Every choice MUST state a concrete conversational stance, tactical proposal, inquiry, or action.
- RELEVANCE & SUBSTANCE-ONLY CHOICES: Output 2 to 5 genuinely meaningful, distinct options. NEVER invent artificial micro-checks or filler options.
- POST-OBJECTIVE TRANSITION: Once a puzzle, check, or obstacle in the current room is resolved, NEVER generate redundant checks to re-study the solved object; pivot immediately to onward travel, NPC guidance, or recovery (`NONE | 0`).
- OPEN HUB & FREE AMBIENT EXPLORATION: Outside active conversation, compose relevant options from: (1) NPC Conversation, (2) Quest/Climax Action if at destination, (3) Scene Sensory Inspection (`NONE | 0`), (4) Ambient Prop Interaction (`NONE | 0`), (5) Travel toward adjacent/waypoint areas (`NONE | 0`), (6) Wilderness scouting (`PER` or `AGI`). NEVER emit dialogue exit choices in Open Exploration mode.
- ITEM & FREE ACTIONS: If a carried inventory item solves the immediate obstacle, offer `ITEM | 0 | ...`. Routine observation, exits, and travel use `NONE | 0`. If `[PRE-TURN SOCIAL SEEDS]` is provided, copy each seed's exact `topic_id=<id>` and `category=<cat>` onto its `@@CHOICES` line—NEVER put raw stat names, DC numbers, or spoiler hints inside choice labels or prose."""

OPENING_ENTITY_RULES = """OPENING SCENE SETUP RULES:
- `new_entities`: Declare every newly introduced named person, place, or faction with canonical name, race, species, gender, appearance, 2-3 traits, motivation, and mannerisms.
- `campaign_end_goals`: Author 3 scenario-relevant long-term victory conditions (`G1`, `G2`, `G3`).
- `npcs_present`: Include only characters physically present in the immediate opening room.
- `choices`: Propose 3-5 concrete, distinct opening actions grounded strictly in the immediate room, present NPCs, and starting hook. Obey the ANTI-DIRECTORY rule (never bare 'Speak with [NPC]' lists) and NEVER copy Sub-Quest or Campaign End Goal titles as choices."""

NARRATIVE_TURN_MODE_RULES = """You are the Game Master for "Hikayat", an interactive text RPG.

CORE ATTRIBUTES: STR (might/force), PER (observation/ranged/stealth sense), END (stamina/resilience), CHA (persuasion/presence), INT (lore/magic/deduction), AGI (reflexes/acrobatics/stealth), LUK (fortune/critical edge).

TURN NARRATION RULES:
- **Checks, Fail-Forward & Ticking Clocks:**
  * Outcomes are pre-rolled deterministically; narrate the exact given check tier (`Critical Success`, `Success`, `Failure`, `Critical Failure`) without deciding success yourself.
  * FAIL-FORWARD: On `Failure`, NEVER write a static dead-end ("nothing happens"). Advance with (1) Complication/Escalation, (2) Success at a Cost (narrative/social friction in non-combat scenes; physical consequences in hazard/combat scenes), or (3) a Tactical Shift/New Lead.
  * On `Critical Failure`, narrate a dramatic setback, ambush trigger, trap, or sharp scene complication.
  * TICKING CLOCKS: High-tension countdown threats (barricades giving way, imminent sweeps, charging traps) must resolve or breach by Turn 3 — never stall "seconds away".
- **Canonical Identity, Naming & Accompanied Travel:**
  * Reuse exact established names from `KNOWN WORLD` and active facility/school rosters (preserving cultural surname/given-name/patronymic order and canonical faction hierarchy names — never invent aliases or nicknames like "The President").
  * Any NPC the player directly approaches, addresses, inspects, or speaks with MUST be referred to by their personal name; background crowds stay unnamed atmosphere. When traveling alongside a partner, name them explicitly upon arrival and keep bystanders from crowding them out.
- **Species Biology, Pronoun Canon & Intimate/Social Boundaries:**
  * Male characters strictly use `he/him/his`; female characters strictly use `she/her/hers` (never invert or use singular `they/them` for canon binary characters).
  * Pure humans/humanoids NEVER exhibit animal ears, tails, fur, paws, claws, or purring; animal traits belong strictly to beastfolk/hybrid species (and beastfolk dyed hair contrasts with their natural body fur/scales).
  * Respect canonical anatomy and undergarment states: if an NPC is Commando or Bra-less, NEVER invent phantom panties or bras; never proactively describe unrevealed intimate traits before disclosure or undressing.
  * When an NPC is asked about romantic history, suitors, or virginity, speak truthfully from their profile (zero fabricated exes for virgins). Romantic banter must respect the protagonist's canon gender.
  * When an inquiry into an NPC's personal or intimate profile (`sensitive_spots`, `turn_ons`, `fetishes`, `intimate_demeanor`, `intimate_dynamic`) SUCCEEDS, voice those concrete details explicitly in dialogue/prose rather than vague placeholders.
- **Forward Temporal Momentum & Dialogue Craft:**
  * `@@OUTCOME` executes ONLY the NEW player action right now — NEVER recap, summarize, or re-quote dialogue/events already in `RECENT HISTORY`. `@@NEXT` moves forward into immediate aftermath and tension without repeating `@@OUTCOME`.
  * Give characters distinct voices, concrete tangible topics/anecdotes, and grounded pacing. STRICTLY BANNED: protagonist sycophancy ("You're different from the others", "It's... refreshing", "mask slipping" in casual talk), artificial universal stutters ("I-I...", "w-what...") unless canonically stuttering, and fourth-wall engine terms (`Sub-Objective #`, `DC check`, `quest log`, `stats`, `NPC`) inside prose or quotes.
- **Caseboard Confrontations:** When speaking with a suspect linked to a verified deduction in `INVESTIGATION EVIDENCE CASEBOARD`, offer a prominent `[REVEAL EVIDENCE]` or `[CONFRONT]` choice in `@@CHOICES`."""

COMBAT_TURN_MODE_RULES = """You are the Game Master in COMBAT ENCOUNTER state.
Active hostile enemies are locked in battle with the party!

COMBAT NARRATION RULES:
- Ground `@@OUTCOME` and `@@NEXT` in visceral, high-stakes action matching the `DETERMINISTIC COMBAT RESULT` directive, equipped weapons/abilities, and battlefield environment.
- STRICT IMMERSION RULE (NO NUMBERS IN PROSE): NEVER write numeric HP/MP values, damage integers, percentages, roll values, or stat/DC numbers inside `@@OUTCOME` or `@@NEXT`. Portray wounds, exhaustion, shields, and stamina strictly through physical sensory prose.
- ENEMY HEALTH & DEFEAT FIDELITY:
  * If `DETERMINISTIC COMBAT RESULT` shows an enemy still has HP > 0, that enemy is STILL ALIVE, STANDING, AND FIGHTING (describe wounds or stagger, NEVER premature death/collapse).
  * If declared `ENEMY DEFEATED` (HP <= 0), narrate that enemy's decisive defeat, collapse, or banishment this turn.
- On failed player checks, narrate the enemy's retaliation or tactical counter-attack faithfully.
- Do NOT generate investigation clues during active combat, and do NOT emit `@@CHOICES` during active combat (tactical combat decks are supplied by the engine)."""

@functools.cache
def build_static_core(mode: Mode, kind: Kind) -> str:
    """Z0a + Z0b. Pure function of constants, so it is byte-identical in every process."""
    from llm_client import GM_SHARED_RULES                       # lazy: avoids import cycles
    from game_engine.schemas import (
        COMBAT_SENTINEL_FORMAT,
        NARRATIVE_SENTINEL_FORMAT,
        SCENE_SCHEMA,
    )
    from mechanics.combat.core import COMBAT_SYSTEM_PROMPT, COMBAT_CHOICE_SCHEMA
    import json
    if kind == "turn":
        mode_block = COMBAT_TURN_MODE_RULES if mode == "combat" else NARRATIVE_TURN_MODE_RULES
        schema = COMBAT_SENTINEL_FORMAT if mode == "combat" else NARRATIVE_SENTINEL_FORMAT
        tail = [TURN_OUTPUT_RULES]
        if mode == "narrative":
            tail.append(NARRATIVE_CHOICE_CRAFT_RULES)
        schema_hdr = f"OUTPUT SCHEMA (respond matching this exact section format — NO JSON fences or braces):\n{schema}"
    else:
        mode_block = (
            COMBAT_SYSTEM_PROMPT
            if mode == "combat"
            else (
                NARRATIVE_TURN_MODE_RULES
                .replace("`@@OUTCOME`", "`narrative`")
                .replace("`@@NEXT`", "`narrative`")
                .replace("`@@CHOICES`", "`choices`")
                .replace("@@OUTCOME", "narrative")
                .replace("@@NEXT", "narrative")
                .replace("@@CHOICES", "choices")
            )
        )
        schema = json.dumps(COMBAT_CHOICE_SCHEMA) if mode == "combat" else SCENE_SCHEMA
        tail = [OPENING_ENTITY_RULES] if mode == "narrative" else []
        schema_hdr = f"OUTPUT SCHEMA (respond with JSON matching this):\n{schema}"
    return SEP.join([GM_SHARED_RULES, mode_block, *tail, schema_hdr])

def _is_female_gender(raw_gender: str | None) -> bool:
    val = str(raw_gender or "").lower().strip()
    return any(kw in val for kw in ("fem", "woman", "girl", "lady", "she", "kobieta", "perempuan", "wanita"))


def _style_voice_directive_for_lang(
    lang: str,
    eff_style: str,
    *,
    is_sms: bool = False,
) -> str:
    """Return style-aware register & slang localization instructions for a language code."""
    if lang == "ms":
        if eff_style == "brainrot":
            base = (
                "- STYLE OVERRIDE (BRAINROT — MALAYSIAN GEN-Z/ALPHA SLANG): Write in chaotic, funny casual Bahasa Melayu (`kau`/`aku`/`bro`/`member`) blending ALL THREE layers:\n"
                "  1. Native MY internet/TikTok slang (`koyak`, `padu`, `pishang`, `barai`, `palatau`, `terpaling`, `mantap mat`).\n"
                "  2. Deadpan literal Malay translations for English meme idioms (`GOAT` -> `kambing`, `cook`/`cooked`/`let him cook` -> `masak`/`kena masak`/`biar dia masak`, `touch grass` -> `sentuh rumput`, `locked in` -> `kunci habis`, `no cap` -> `tiada topi`).\n"
                "  3. Direct untranslated brainrot loanwords where no literal Malay equivalent exists (`rizz`, `Ohio`, `skibidi`, `gyatt`, `mogging`, `mewing`, `delulu`, `aura`, `sigma`, `fanum tax`).\n"
                "- Keep physical actions clear and followable; rotate ~2-4 fresh slang hits per paragraph (1-2 in short texts) without spamming one catchphrase every line."
            )
            return base
        if eff_style == "shakespearean":
            return (
                "- STYLE OVERRIDE (SHAKESPEAREAN — HIKAYAT KLASIK / ISTANA): Use elevated theatrical Classical Malay "
                "(`hamba`, `tuan hamba`, `gerangan`, `adinda`/`kakanda`, `hatta`, `syahadan`, `arakian`) with dramatic courtly metaphors and poetic rhythm."
            )
        if eff_style == "noir":
            if is_sms:
                return (
                    "- STYLE OVERRIDE (NOIR SMS): Write casual mobile texting (`awak`/`kau`/`aku`) colored with subtle cynical detective wit — keep text-message brevity and natural rhythm."
                )
            return (
                "- STYLE OVERRIDE (NOIR — DETEKTIF KELAM): Write narrator prose with crisp, cynical Bahasa Melayu hardboiled metaphors and rain-and-shadow mood; keep NPC quotes in-persona."
            )
        if eff_style == "witty":
            if is_sms:
                return (
                    "- STYLE OVERRIDE (WITTY SMS): Write casual mobile texting (`awak`/`kau`/`aku`) with dry, clever deadpan irony (no internet meme slang)."
                )
            return (
                "- STYLE OVERRIDE (WITTY — SATIRA BERSAHAJA): Write narrator prose with dry, ironic Bahasa Melayu deadpan humor (no modern internet meme slang); keep NPC quotes in-persona."
            )
        return (
            "- Use natural, conversational Bahasa Melayu mobile texting / social media register (relaxed everyday phrasing such as 'awak'/'kau'/'saya' suited to closeness, natural particles like 'lah'/'kan' when casual — avoid stiff formal textbook prose or unprompted English switching)."
            if is_sms else
            "- Use evocative, natural Bahasa Melayu RPG prose ('kamu' or 'anda' adapted to tone and setting, clear modern phrasing)."
        )

    if lang == "zh":
        if eff_style == "brainrot":
            return (
                "- STYLE OVERRIDE (BRAINROT — 中文抽象热梗): Write in high-energy Simplified Chinese Gen-Z / internet meme style ('你' for protagonist), "
                "blending 抽象梗 (`破防`, `硬控`, `红温`, `汗流浃背`, `纯小丑`, `拉满`, `包的`, `顶级理解`, `小丑竟是我自己`, plus loanwords like `aura`/`rizz` when fitting). "
                "Keep physical action clear and rotate ~2-4 fresh hits per paragraph without unreadable gibberish."
            )
        if eff_style == "shakespearean":
            return (
                "- STYLE OVERRIDE (SHAKESPEAREAN — 古风戏剧半文白): Write in theatrical classical Simplified Chinese stage prose "
                "(`汝`, `阁下`, `岂非`, `嗟夫`, `何其`, poetic classical metaphors and dramatic rhythm)."
            )
        if eff_style == "noir":
            if is_sms:
                return (
                    "- STYLE OVERRIDE (NOIR SMS): Write casual Simplified Chinese mobile texting colored with cynical noir edge and brief punchy lines."
                )
            return (
                "- STYLE OVERRIDE (NOIR — 冷硬派侦探): Write narrator prose in punchy, cynical Simplified Chinese noir ('你'), keeping NPC quotes true to each character."
            )
        if eff_style == "witty":
            if is_sms:
                return (
                    "- STYLE OVERRIDE (WITTY SMS): Write casual Simplified Chinese mobile texting with dry, clever deadpan humor (no internet meme slang)."
                )
            return (
                "- STYLE OVERRIDE (WITTY — 冷面反讽): Write narrator prose with dry deadpan irony and wit ('你'), avoiding modern internet slang while keeping NPC quotes in-persona."
            )
        return (
            "- Use natural everyday Simplified Chinese mobile chat / social media phrasing."
            if is_sms else
            "- Use natural, evocative Simplified Chinese RPG prose ('你' for second-person)."
        )

    if lang == "pl":
        if eff_style == "brainrot":
            return (
                "- STYLE OVERRIDE (BRAINROT — POLSKI SLANG GEN-Z/ALPHA): Write in chaotic, funny Polish youth/internet slang "
                "(`rel`, `essa`, `odklejka`, `baza`, `ugotowany`, `dojechany`, `sigma`, `aura`, `rizz`, `delulu`, `Ohio`, `skibidi`) "
                "while strictly preserving protagonist grammatical gender verb/adjective endings and keeping physical actions clear (~2-4 rotated slang hits per paragraph)."
            )
        if eff_style == "shakespearean":
            return (
                "- STYLE OVERRIDE (SHAKESPEAREAN — STYL STAROPOLSKI / TEATRALNY): Write in elevated theatrical Polish drama cadence "
                "(`aliści`, `zaiste`, `waćpan`/`waćpanna`, `azaliż`, poetic stage metaphors) while strictly preserving protagonist grammatical gender endings."
            )
        if eff_style == "noir":
            if is_sms:
                return (
                    "- STYLE OVERRIDE (NOIR SMS): Write natural Polish mobile texting (casual 'ty' form) with dry cynical noir wit."
                )
            return (
                "- STYLE OVERRIDE (NOIR — CZARNY KRYMINAŁ): Write narrator prose in punchy, cynical Polish noir style; keep NPC quotes in each character's own voice."
            )
        if eff_style == "witty":
            if is_sms:
                return (
                    "- STYLE OVERRIDE (WITTY SMS): Write natural Polish mobile texting (casual 'ty' form) with dry deadpan irony (no internet meme slang)."
                )
            return (
                "- STYLE OVERRIDE (WITTY — SUCHA SATYRA): Write narrator prose with dry, ironic Pratchett-style Polish wit (no meme slang); keep NPC quotes in-persona."
            )
        return (
            "- Use natural, everyday Polish mobile texting / social timeline phrasing (casual 'ty' form, natural colloquialisms, zero stiff bookish prose)."
            if is_sms else
            "- Use natural, immersive Polish RPG prose."
        )

    if lang == "de":
        if eff_style == "brainrot":
            return (
                "- STYLE OVERRIDE (BRAINROT — DEUTSCHES JUGENDWORT / GEN-Z SLANG): Write in chaotic, comedic German internet slang ('du' form) "
                "blending Jugendwort & meme terms (`digga`, `lost`, `aura`, `wild`, `gecooked`, `stabil`, `cringe`, `rizz`, `delulu`, `locked in`, `skibidi`, `Ohio`). "
                "Keep physical action followable and rotate ~2-4 fresh hits per paragraph."
            )
        if eff_style == "shakespearean":
            return (
                "- STYLE OVERRIDE (SHAKESPEAREAN — KLASSISCHES BÜHNENDEUTSCH): Write in theatrical Early-Modern / Schiller-Goethe German drama cadence "
                "(`fürwahr`, `wohlan`, `ward`, `dünkt`, elevated stage metaphors) using 'du'/'euch' dramatically."
            )
        if eff_style == "noir":
            if is_sms:
                return (
                    "- STYLE OVERRIDE (NOIR SMS): Write casual German mobile texting ('du' form) with dry cynical noir wit."
                )
            return (
                "- STYLE OVERRIDE (NOIR — HARTGESOTTENER KRIMI): Write narrator prose in cynical, punchy German noir ('du' form); keep NPC quotes in-persona."
            )
        if eff_style == "witty":
            if is_sms:
                return (
                    "- STYLE OVERRIDE (WITTY SMS): Write casual German mobile texting ('du' form) with dry deadpan irony (no internet meme slang)."
                )
            return (
                "- STYLE OVERRIDE (WITTY — TROCKENER SPOTT): Write narrator prose with dry deadpan irony ('du' form, zero internet slang); keep NPC quotes in-persona."
            )
        return (
            "- Use natural everyday German mobile chat / social media phrasing ('du' form)."
            if is_sms else
            "- Use natural, immersive German RPG prose ('du' form)."
        )

    # English SMS style override (brainrot / shakespearean / noir / witty in SMS mode)
    if is_sms and eff_style == "brainrot":
        return (
            "- STYLE OVERRIDE (BRAINROT SMS): Write messages/posts in comedic Gen-Z / Alpha internet slang "
            "(`cooked`, `locked in`, `aura`, `rizz`, `delulu`, `no cap`, `fr`, `crashout`, `Ohio`, `skibidi`) matching the speaker's personality."
        )
    if is_sms and eff_style == "shakespearean":
        return (
            "- STYLE OVERRIDE (SHAKESPEAREAN SMS): Write playful theatrical Elizabethan messages/posts "
            "(`thee`, `thou`, `dost`, `hath`, `forsooth`) while keeping JSON keys and canonical names intact."
        )
    if is_sms and eff_style == "noir":
        return (
            "- STYLE OVERRIDE (NOIR SMS): Write brief mobile messages/posts with dry, cynical hardboiled wit matching the speaker."
        )
    if is_sms and eff_style == "witty":
        return (
            "- STYLE OVERRIDE (WITTY SMS): Write brief mobile messages/posts with dry deadpan irony (no modern internet meme slang)."
        )
    return ""


def build_language_directive(session: dict, kind: Kind = "turn") -> str:
    from game_engine.prompts import resolve_style_and_pacing
    lang = str(session.get("narration_language") or session.get("language") or "en").lower().strip().split("-")[0]
    eff_style, _, _ = resolve_style_and_pacing(session)
    is_opening = kind == "opening"
    fields_clause = (
        "`narrative`, `scene_title`, and all `choices.label`"
        if is_opening else
        "the `@@TITLE` heading, `@@OUTCOME` and `@@NEXT` prose, and all `@@CHOICES` action labels"
    )
    schema_rule = (
        "Keep all JSON keys (e.g. 'narrative', 'choices'), stat abbreviations (STR, PER, END, CHA, INT, AGI, LUK, NONE), and status effect codes strictly in English."
        if is_opening else
        "Keep all section headers (`@@TITLE:`, `@@OUTCOME`, `@@NEXT`, `@@CHOICES`, `@@META`), `@@META` keys (`memory:`, `pose:`, `cast:`, `epistemic:`), and stat abbreviations (STR, PER, END, CHA, INT, AGI, LUK, ITEM, NONE) strictly in English."
    )
    style_line = _style_voice_directive_for_lang(lang, eff_style, is_sms=False)
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
        return (
            "LANGUAGE DIRECTIVE: POLISH (Język polski)\n"
            f"- Output {fields_clause} strictly in natural, immersive Polish.\n"
            f"{style_line}\n"
            f"- GRAMMATICAL GENDER: {gender_inflection}\n"
            f"- CRITICAL SCHEMA RULE: {schema_rule}\n"
            "- Procedural items, weapon descriptors, and NPC titles must be in natural Polish (e.g. 'Żelazny miecz', 'Karczmarz', 'Mikstura leczenia'). Keep proper character names and place names intact."
        )
    elif lang == "ms":
        return (
            "LANGUAGE DIRECTIVE: MALAY (Bahasa Melayu)\n"
            f"- Output {fields_clause} strictly in Bahasa Melayu matching the active Narrative Style.\n"
            f"{style_line}\n"
            f"- CRITICAL SCHEMA RULE: {schema_rule}\n"
            "- Procedural items, weapon descriptors, and NPC titles must be in natural Malay (e.g. 'Pedang Besi', 'Pemilik Kedai', 'Penawar Luka'). Keep proper character names and place names intact."
        )
    elif lang == "zh":
        return (
            "LANGUAGE DIRECTIVE: CHINESE MANDARIN (中文 / 简体中文)\n"
            f"- Output {fields_clause} strictly in Simplified Chinese matching the active Narrative Style.\n"
            f"{style_line}\n"
            f"- CRITICAL SCHEMA RULE: {schema_rule}\n"
            "- Procedural items, weapon descriptors, and NPC titles must be in natural Chinese (e.g. '铁剑', '客栈掌柜', '治疗药水'). Keep proper character names and place names intact."
        )
    elif lang == "de":
        return (
            "LANGUAGE DIRECTIVE: GERMAN (Deutsch)\n"
            f"- Output {fields_clause} strictly in German matching the active Narrative Style.\n"
            f"{style_line}\n"
            f"- CRITICAL SCHEMA RULE: {schema_rule}\n"
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
    from game_engine.prompts import resolve_style_and_pacing
    lang = str(session.get("narration_language") or session.get("language") or "en").lower().strip().split("-")[0]
    eff_style, _, _ = resolve_style_and_pacing(session)

    # Persistent canon subsystems (style="narrative": quests, bounties, digests) never receive slang/archaic overrides.
    # Ephemeral SMS/feed channels (style="sms") receive brainrot/shakespearean voice even in English.
    if lang == "en":
        if style == "sms" and eff_style in ("brainrot", "shakespearean", "noir", "witty"):
            en_voice = _style_voice_directive_for_lang("en", eff_style, is_sms=True)
            fields_target = (
                ", ".join(f"`{f}`" for f in text_fields)
                if text_fields
                else "all message/post text values"
            )
            preserve_note = "Keep all JSON keys, proper character names, and canonical location paths strictly intact."
            if preserve_fields:
                preserve_note += f" Keep {', '.join(f'`{f}`' for f in preserve_fields)} strictly unchanged."
            return (
                "PHONE VOICE DIRECTIVE:\n"
                f"- Apply to {fields_target}.\n"
                f"{en_voice}\n"
                f"- CRITICAL SCHEMA RULE: {preserve_note}"
            )
        return ""

    if lang not in ("pl", "ms", "zh", "de"):
        return ""

    effective_side_style = eff_style if style == "sms" else "normal"

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
            register_line = _style_voice_directive_for_lang("pl", effective_side_style, is_sms=True) + "\n"
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
        register_line = _style_voice_directive_for_lang("ms", effective_side_style, is_sms=(style == "sms")) + "\n"
        return (
            "LANGUAGE DIRECTIVE: MALAY (Bahasa Melayu)\n"
            f"- Output {fields_target} strictly in Bahasa Melayu.\n"
            f"{register_line}"
            f"- CRITICAL SCHEMA RULE: {preserve_note}"
        )

    if lang == "zh":
        register_line = _style_voice_directive_for_lang("zh", effective_side_style, is_sms=(style == "sms")) + "\n"
        return (
            "LANGUAGE DIRECTIVE: CHINESE MANDARIN (中文 / 简体中文)\n"
            f"- Output {fields_target} strictly in Simplified Chinese.\n"
            f"{register_line}"
            f"- CRITICAL SCHEMA RULE: {preserve_note}"
        )

    # lang == "de"
    register_line = _style_voice_directive_for_lang("de", effective_side_style, is_sms=(style == "sms")) + "\n"
    return (
        "LANGUAGE DIRECTIVE: GERMAN (Deutsch)\n"
        f"- Output {fields_target} strictly in German.\n"
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

def build_scenario_genre_zone_rules(session: dict, kind: Kind = "turn") -> str:
    """Z1: scope genre archetypes, peer boundaries, and combat recruitment to the active scenario."""
    import scenario_data
    scen = session.get("scenario")
    tags = {str(t).lower() for t in (scenario_data.get_scenario_tags(scen) or [])}
    choices_ref = "`choices`" if kind == "opening" else "`@@CHOICES`"
    rules: list[str] = []

    if scenario_data.is_combat_enabled(scen):
        rules.append(
            "PARTY COMPANION RECRUITMENT (COMBAT SCENARIOS): When conversing with a friendly, neutral, or allied NPC "
            f"(and party size is under 4), offer a [CHA] skill check in {choices_ref} to invite them to team up using natural "
            "phrasing ('team up', 'partner up', 'join your field team/retinue/crew') — never meta-phrases like 'as a permanent companion'."
        )
    if scenario_data.is_high_school_scenario(scen) or not scenario_data.is_combat_enabled(scen):
        rules.append(
            "SOCIAL & PEER ELIGIBILITY: Romantic routes, contact affinity, and phone directory entries are strictly reserved for "
            "peers/contemporaries (classmates, club peers, equals). Faculty, parents, and store clerks are story-only figures."
        )
    if scenario_data.is_nsfw_scenario(scen):
        rules.append(
            "MATURE SCENE & PLAYER CLIMAX PRIMACY: Match intimacy pacing, character dynamic (`intimate_demeanor` / `intimate_dynamic`), "
            "and canonical undergarment state faithfully; avoid generic stuttering clichés. During active intercourse/intimacy, an NPC partner's climax "
            "is a mid-scene peak that intensifies the act and NEVER ends the encounter or triggers post-coital collapse/aftercare until the PLAYER climaxes "
            f"or explicitly withdraws; keep active continuation options (`END`/`STR`/`AGI`/`CHA`) plus at most one `NONE | 0` gentle pause/withdraw option in {choices_ref}."
        )
    if "space" in tags or "cyberpunk" in tags or "sci_fi" in tags:
        rules.append("GENRE TEXTURE: Ground scenes in sci-fi/cyberpunk motifs (netrunning, telemetry, salvage, corporate intrigue).")
    elif "post_apocalypse" in tags:
        rules.append("GENRE TEXTURE: Ground scenes in survival scarcity, signal recovery, radiation hazards, and wasteland factions.")

    return "\n".join(rules)


def build_session_zone(session: dict, kind: Kind = "turn") -> str:
    """Z1: changes only when scenario / style settings change."""
    import game_engine
    from mechanics.combat.merchant import merchant_prompt_note
    return SEP.join(p.strip() for p in [
        game_engine._scenario_block(session),
        game_engine._style_block(session, kind=kind),
        build_scenario_genre_zone_rules(session, kind=kind),
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


def _format_epoch_party_vitals(party: list | None) -> str:
    lines: list[str] = []
    for entry in (party or []):
        char = entry[0] if isinstance(entry, (tuple, list)) and entry else entry
        inv_list = entry[1] if isinstance(entry, (tuple, list)) and len(entry) > 1 and isinstance(entry[1], list) else []
        if not isinstance(char, dict) or not char.get("name"):
            continue
        nm = str(char.get("name") or "Hero")
        hp = char.get("hp", 0)
        max_hp = char.get("max_hp", 0)
        mp = char.get("mp", 0)
        max_mp = char.get("max_mp", 0)
        gold = char.get("gold", 0)
        effs = [str(e.get("name") if isinstance(e, dict) else e) for e in (char.get("status_effects") or []) if e]
        eff_str = f", Status: {', '.join(effs)}" if effs else ""
        inv_names = [
            str(it.get("item_name") or it.get("name") or "").strip()
            for it in inv_list
            if isinstance(it, dict) and str(it.get("item_name") or it.get("name") or "").strip()
        ]
        inv_str = f", Carried: {', '.join(inv_names[:12])}" if inv_names else ", Carried: Empty"
        lines.append(f"- {nm}: HP {hp}/{max_hp}, MP {mp}/{max_mp}, Gold {gold}{eff_str}{inv_str}")
    return "\n".join(lines)


def _party_build_signature(party: list | None) -> str:
    """Compact signature of level, stats, equipped gear, and known spells for Z2 invalidation."""
    parts: list[str] = []
    for entry in (party or []):
        char = entry[0] if isinstance(entry, (tuple, list)) and entry else entry
        if not isinstance(char, dict) or not char.get("name"):
            continue
        lvl = char.get("level", 1)
        stats = ",".join(
            str(char.get(k, char.get(k.rstrip("_"), 5)))
            for k in ("str_", "per_", "end_", "cha", "int_", "agi", "luk")
        )
        eq = char.get("equipment")
        eq_sig = (
            ",".join(f"{k}:{v}" for k, v in sorted(eq.items()) if v)
            if isinstance(eq, dict)
            else f"{char.get('equipped_weapon', '')}/{char.get('equipped_armor', '')}"
        )
        raw_spells = char.get("spells") or char.get("learned_spells") or []
        sp_names = ",".join(
            sorted(
                str(sp.get("name") if isinstance(sp, dict) else sp).strip()
                for sp in raw_spells
                if sp
            )
        )
        parts.append(f"{char.get('name')}:{lvl}:{stats}:{eq_sig}:{sp_names}")
    return "|".join(parts)


def _extract_arrived_npc_profiles(fresh_zone_2: str, arrived_npcs: list[str]) -> str:
    if not fresh_zone_2 or not arrived_npcs:
        return ""
    targets = [n.lower() for n in arrived_npcs if n]
    matched: list[str] = []
    for line in str(fresh_zone_2).splitlines():
        s_line = line.strip()
        if not s_line:
            continue
        low_l = s_line.lower()
        if any(t in low_l for t in targets) and s_line not in matched:
            matched.append(s_line)
    if not matched:
        return ""
    return _cap("\n".join(matched), 600)


def resolve_prompt_epoch(
    *,
    session: dict | None,
    mode: Mode,
    scene_loc: str,
    party: list | None,
    present_npc_names: list[str] | None,
    fresh_zone_2: str,
    phys_prompt_block: str,
    time_prompt_block: str,
    active_quests_str: str,
    quest_board_text: str,
    rumors_z3: str,
    trimmed_history: str,
    active_recall_text: str,
    last_turn_summary: str = "",
    enemy_names: list[str] | None = None,
    enemies_str: str = "",
) -> tuple[str, str, dict | None]:
    """
    Hybrid Rolling Epoch KV Cache manager (6-turn horizon with anti-ghosting reset).

    Freezes `zone_2` at `z2_baseline` across consecutive turns in the same scene/mode/settings
    when no present NPC or combat enemy has departed/been defeated, and shifts turn deltas
    (vitals, live enemies, clock, poses, quest/board updates, newly arrived NPCs) into `Z3`
    user_prompt so `Z0 + Z1 + Z1b + Z2` stays byte-identical.
    """
    default_prefix = (
        f"{active_quests_str}"
        f"{quest_board_text}"
        f"{rumors_z3}"
        f"RECENT HISTORY:\n{trimmed_history}{active_recall_text}\n\n"
    )
    if not isinstance(session, dict) or not session.get("id"):
        return fresh_zone_2, default_prefix, None

    try:
        turn_num = int(session.get("_target_turn") or (int(session.get("turn_count") or 0) + 1))
    except (TypeError, ValueError):
        turn_num = 1

    from game_engine.prompts import resolve_style_and_pacing
    eff_style, eff_pacing, eff_dialogue = resolve_style_and_pacing(session)
    style_triplet = f"{eff_style}|{eff_pacing}|{eff_dialogue}"
    settings_sig = (
        f"{style_triplet}|"
        f"{session.get('narration_language') or session.get('language') or 'en'}|"
        f"{_party_build_signature(party)}"
    )
    prev_epoch = session.get("prompt_epoch")

    style_shift_note = ""
    if bool(session.get("history")) and isinstance(prev_epoch, dict) and prev_epoch.get("settings_sig"):
        prev_parts = str(prev_epoch.get("settings_sig") or "").split("|")
        if len(prev_parts) >= 5:
            prev_triplet = "|".join(prev_parts[:3])
        elif len(prev_parts) >= 2:
            p_st, p_pa, p_dl = resolve_style_and_pacing(verbosity=prev_parts[0], dialogue_mode=prev_parts[1])
            prev_triplet = f"{p_st}|{p_pa}|{p_dl}"
        else:
            prev_triplet = ""
        if prev_triplet and prev_triplet != style_triplet:
            style_shift_note = (
                f"[STYLE SHIFT OVERRIDE: The player just switched Narrative Style/Pacing/Dialogue to "
                f"style={eff_style}, pacing={eff_pacing}, dialogue={eff_dialogue}. "
                f"Ignore the paragraph length, vocabulary register, slang, and dialogue density of RECENT HISTORY — "
                f"apply ONLY the new active directives starting THIS turn!]\n\n"
            )
    if style_shift_note:
        default_prefix = f"{default_prefix}{style_shift_note}"

    present_clean: list[str] = []
    seen_low: set[str] = set()
    for raw_n in (present_npc_names or []):
        clean_n = str(raw_n or "").strip()
        if not clean_n or clean_n.lower() == "none":
            continue
        low_n = clean_n.lower()
        if low_n not in seen_low:
            seen_low.add(low_n)
            present_clean.append(clean_n)

    enemies_clean: list[str] = []
    seen_enemies_low: set[str] = set()
    for raw_e in (enemy_names or []):
        clean_e = str(raw_e or "").strip()
        if not clean_e or clean_e.lower() == "none":
            continue
        low_e = clean_e.lower()
        if low_e not in seen_enemies_low:
            seen_enemies_low.add(low_e)
            enemies_clean.append(clean_e)

    loc_str = str(scene_loc or "")
    can_reuse = False
    if (
        bool(session.get("history"))
        and isinstance(prev_epoch, dict)
        and prev_epoch.get("z2_baseline")
        and prev_epoch.get("mode") == mode
        and prev_epoch.get("location") == loc_str
        and prev_epoch.get("settings_sig") == settings_sig
    ):
        try:
            prev_last = int(prev_epoch.get("last_turn_count") or 0)
            start_turn = int(prev_epoch.get("epoch_start_turn") or turn_num)
        except (TypeError, ValueError):
            prev_last = 0
            start_turn = turn_num
        prior_known = [
            str(n).strip()
            for n in (prev_epoch.get("known_present_npcs") or [])
            if str(n or "").strip()
        ]
        prior_enemies = [
            str(e).strip()
            for e in (prev_epoch.get("known_enemies") or [])
            if str(e or "").strip()
        ]
        # Anti-ghosting check: any NPC or enemy present earlier in this epoch who left/died must reset Z2.
        no_npc_departed = all(n.lower() in seen_low for n in prior_known)
        no_enemy_removed = all(e.lower() in seen_enemies_low for e in prior_enemies)
        if prev_last + 1 == turn_num and 0 < (turn_num - start_turn) < 6 and no_npc_departed and no_enemy_removed:
            can_reuse = True

    if not can_reuse:
        new_epoch = {
            "epoch_start_turn": turn_num,
            "last_turn_count": turn_num,
            "mode": mode,
            "location": loc_str,
            "settings_sig": settings_sig,
            "baseline_npcs": list(present_clean),
            "known_present_npcs": list(present_clean),
            "known_enemies": list(enemies_clean),
            "z2_baseline": fresh_zone_2,
            "z3_log": "",
        }
        return fresh_zone_2, default_prefix, new_epoch

    prev_log = str(prev_epoch.get("z3_log") or "").strip()
    turn_sum = str(last_turn_summary or "").strip()
    if turn_sum and turn_sum not in prev_log:
        combined_log = f"{prev_log}\n{turn_sum}".strip() if prev_log else turn_sum
    else:
        combined_log = prev_log
    if len(combined_log) > 1800:
        cut_at = combined_log.find("\n", len(combined_log) - 1800)
        combined_log = combined_log[cut_at + 1 :] if cut_at != -1 else combined_log[-1800:]

    baseline_low = {str(b).strip().lower() for b in (prev_epoch.get("baseline_npcs") or []) if str(b).strip()}
    arrived_npcs = [n for n in present_clean if n.lower() not in baseline_low]

    delta_parts: list[str] = ["[CURRENT TURN STATE DELTA — OVERRIDES SYSTEM BASELINE]:"]
    vitals_txt = _format_epoch_party_vitals(party)
    if vitals_txt:
        delta_parts.append(f"Live Party Vitals:\n{vitals_txt}")
    if (enemies_str or "").strip():
        delta_parts.append(f"Live Nearby Enemies (overrides baseline):\n{str(enemies_str).strip()}")
    if time_prompt_block:
        delta_parts.append(str(time_prompt_block).strip())
    if arrived_npcs:
        delta_parts.append(f"Newly Arrived NPCs Now Present: {', '.join(arrived_npcs)}")
        arrived_profiles = _extract_arrived_npc_profiles(fresh_zone_2, arrived_npcs)
        if arrived_profiles:
            delta_parts.append(f"Newly Arrived NPC Profiles:\n{arrived_profiles}")
    if phys_prompt_block:
        delta_parts.append(f"Current Physical & Garment State:\n{str(phys_prompt_block).strip()}")
    if active_quests_str:
        delta_parts.append(str(active_quests_str).strip())
    if quest_board_text:
        delta_parts.append(str(quest_board_text).strip())
    if rumors_z3:
        delta_parts.append(str(rumors_z3).strip())

    delta_block = "\n\n".join(p for p in delta_parts if p)
    epoch_prefix_parts: list[str] = []
    if combined_log:
        hist_text_check = str(trimmed_history or "")
        dedup_lines = [ln for ln in combined_log.splitlines() if ln.strip() and ln.strip() not in hist_text_check]
        if dedup_lines:
            epoch_prefix_parts.append("EPOCH TURN LOG:\n" + "\n".join(dedup_lines))
    epoch_prefix_parts.append(f"RECENT HISTORY:\n{trimmed_history}{active_recall_text}".rstrip())
    epoch_prefix_parts.append(delta_block)
    user_prefix = "\n\n".join(epoch_prefix_parts) + "\n\n"

    merged_known = list(dict.fromkeys([*(prev_epoch.get("known_present_npcs") or []), *present_clean]))
    merged_enemies = list(dict.fromkeys([*(prev_epoch.get("known_enemies") or []), *enemies_clean]))
    new_epoch = {
        **prev_epoch,
        "last_turn_count": turn_num,
        "known_present_npcs": merged_known,
        "known_enemies": merged_enemies,
        "z3_log": combined_log,
    }
    return str(prev_epoch["z2_baseline"]), user_prefix, new_epoch


CLOSING_REMINDER = (
    "Respond using the exact @@TITLE / @@OUTCOME / @@NEXT sentinel sections matching the OUTPUT SCHEMA "
    "in the system prompt, obeying the TURN OUTPUT REQUIREMENTS and the active STYLE & DIALOGUE directives."
)


def build_closing_reminder(session: dict | None = None) -> str:
    """Append a low-volatility-free Z3 tail micro-quota anchor without busting Z0-Z2 KV caches."""
    from game_engine.prompts import resolve_style_and_pacing
    eff_style, eff_pacing, eff_dialogue = resolve_style_and_pacing(session)
    quota_map = {
        "concise": "1 short para @@OUTCOME (2-3 sent) + 1 short para @@NEXT (2-3 sent), snappy 8-14w choices",
        "balanced": "1-2 paras @@OUTCOME + 2-3 paras @@NEXT, 15-22w choices",
        "novelistic": "2-3 paras @@OUTCOME + 3-4 slow-burn paras @@NEXT, 18-25w choices",
    }
    dlg_map = {
        "off": "ZERO spoken quotes",
        "minimal": "max 1-2 brief quotes",
        "balanced": "2-3 two-way quoted turns",
        "adaptive": "combat barks / 2-3 two-way social quotes",
        "rich": "3-5 natural prose-woven banter quotes (no **Name**: script)",
        "script": "3-5 stage-script lines (**Name** *(action)*: \"Quote\")",
    }
    quota_hint = quota_map.get(eff_pacing, quota_map["balanced"])
    dlg_hint = dlg_map.get(eff_dialogue, dlg_map["adaptive"])
    return (
        f"{CLOSING_REMINDER}\n"
        f"[ACTIVE NARRATION QUOTA: style={eff_style} | pacing={eff_pacing} ({quota_hint}) | "
        f"dialogue={eff_dialogue} ({dlg_hint}) — keep @@META, 3-tier location paths, "
        f"new_entities.description, and quest clues in clean grounded canon.]"
    )
