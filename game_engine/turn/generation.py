from .constants import *
import db
import re
import json
import scenario_data
from mechanics.world.locations import *
from mechanics.social.persona import *
from mechanics.narrative.intent import *
from game_engine.core import SYSTEM_PROMPT, SCENE_SCHEMA, VALID_STATS, is_nsfw_scenario
import namegen
import random
import logging
log = logging.getLogger(__name__)
import game_engine
from db import adb
import asyncio
from game_engine.turn_context import TurnContext
from models.llm_schemas import TurnOutcome, ActionClassification, OpeningScene

def get_narrative_requirements(verbosity: str, dialogue_mode: str) -> str:

    """Generate dynamic NARRATIVE REQUIREMENTS text based on the session's verbosity setting.

    This enforces paragraph quotas and vocabulary tone matching the player's active STYLE preference.

    """

    _outcome_reqs = {

        "concise": (

            "`outcome_narrative`: Exactly 1 punchy paragraph (2-3 sentences max). "

            "STRICTLY FORBIDDEN: Do NOT write multiple paragraphs, purple prose, or filler."

        ),

        "direct": (

            "`outcome_narrative`: 1-2 tight paragraphs. Momentum-driven, concrete action and consequences only. "

            "STRICTLY FORBIDDEN: Do NOT use flowery metaphors, novelistic padding, or archaic vocabulary."

        ),

        "normal": (

            "`outcome_narrative`: 1-2 clear paragraphs using contemporary modern language. "

            "STRICTLY FORBIDDEN: Do NOT use purple prose, archaic words, or overwrought sensory descriptions."

        ),

        "vivid": (

            "`outcome_narrative`: 1-2 rich, atmospheric paragraphs with sensory detail and evocative prose. "

            "STRICTLY FORBIDDEN: Do NOT write flat, dry, or rushed summaries."

        ),

        "shakespearean": (

            "`outcome_narrative`: 1-2 paragraphs in theatrical Elizabethan English with archaic vocabulary and dramatic cadence. "

            "STRICTLY FORBIDDEN: Do NOT use modern colloquialisms or casual phrasing."

        ),

    }

    _next_reqs = {

        "concise": (

            "`next_narrative`: Exactly 1 compact paragraph (2-3 sentences max) covering the scene's next state. "

            "STRICTLY FORBIDDEN: Do NOT pad with atmospheric filler, extended description, or purple prose."

        ),

        "direct": (

            "`next_narrative`: Exactly 2 direct paragraphs. Cover immediate scene aftermath and tension without filler. "

            "STRICTLY FORBIDDEN: Do NOT write philosophical ramblings or extended atmospheric scene-painting."

        ),

        "normal": (

            "`next_narrative`: 2-3 clear paragraphs using contemporary modern language with balanced pacing. "

            "STRICTLY FORBIDDEN: Do NOT use purple prose, melodramatic tropes, or ornate decorative language."

        ),

        "vivid": (

            "`next_narrative`: 2-3 rich, immersive paragraphs with sensory atmosphere and evocative detail. "

            "STRICTLY FORBIDDEN: Do NOT write flat, mechanical, or rushed summaries."

        ),

        "shakespearean": (

            "`next_narrative`: 2-3 paragraphs in theatrical Elizabethan English with archaic vocabulary, elaborate metaphors, and dramatic stage-play cadence. "

            "STRICTLY FORBIDDEN: Do NOT use modern slang or casual contemporary phrasing."

        ),

    }

    _dialogue_reqs = {

        "off": "Do NOT include any spoken dialogue or quotation marks in any narrative field.",

        "minimal": "Include at most 1-2 short spoken quotes total across both narrative fields. STRICTLY FORBIDDEN: No extended exchanges.",

        "balanced": (

            "When the player character interacts with or speaks to an NPC, write BOTH characters speaking aloud in direct quotes — "

            "at least 2-3 back-and-forth spoken turns. STRICTLY FORBIDDEN: Do NOT write only the NPC's quote while summarizing the player character's words in third-person."

        ),

        "adaptive": (

            "In social/investigation/romance contexts: write at least 2-3 back-and-forth spoken turns between BOTH the player character and NPC. "

            "In combat contexts: short tactical callouts only. STRICTLY FORBIDDEN: In social scenes, do NOT reduce conversation to a single NPC quote."

        ),

        "rich": (

            "Drive narrative primarily through direct two-way spoken dialogue. Write at least 3-5 back-and-forth exchanges between the player character and NPCs, "

            "formatted as **Name** *(action)*: \"Quote\". STRICTLY FORBIDDEN: Do NOT bury dialogue under walls of prose."

        ),

    }

    v = verbosity if verbosity in _outcome_reqs else "vivid"

    d = dialogue_mode if dialogue_mode in _dialogue_reqs else "balanced"

    return (

        f"- {_outcome_reqs[v]}\n"

        f"- {_next_reqs[v]}\n"

        f"- DIALOGUE RULE: {_dialogue_reqs[d]}"

    )

async def generate_opening_scene(session: dict, party: list) -> OpeningScene:

    scenario = game_engine.get_session_scenario(session)

    scen_key = session.get("scenario", "fantasy")

    first_char_name = party[0][0].get("name", "") if party and isinstance(party[0], (tuple, list)) and isinstance(party[0][0], dict) else (party[0].get("name", "") if party and isinstance(party[0], dict) else "")



    # Retrieve randomized starting hook and archetype (Hub Launchpad, In Media Res, or Delve Threshold)

    hook_context = scenario_data.get_dynamic_starting_hook(scenario, session_id=session["id"], char_name=first_char_name)

    arch_key = hook_context.get("archetype", "hub_launchpad")

    arch_title = arch_key.replace("_", " ").title()

    hook_text = hook_context.get("hook_text", "")

    suggested_loc = hook_context.get("suggested_location", "")

    arch_directive = hook_context.get("directive", "")



    # Don't pre-create a story quest here -- the opening scene LLM will generate title & objective

    # Only check if one already exists (e.g. session resumed mid-adventure)

    ctx = TurnContext(session.get("id"), session)
    existing_sq = ctx.story_quest

    if existing_sq:

        story_quest_context = (

            f"- **Quest ID:** {existing_sq['quest_id']}\n"

            f"- **Title:** {existing_sq['title']}\n"

            f"- **Objective:** {existing_sq['objective']}\n"

            f"- **Clues Discovered (0/3):**\n• No clues discovered yet."

        )

    else:

        story_quest_context = "No active Story Quest yet. You MUST generate one in the opening scene via the `story_quest` JSON field."

    side_bounties_context = "No active side bounties."



    scenario_context = (

        f"{game_engine._scenario_block(session)}\n"

        f"OPENING INCITING INCIDENT [{arch_title}]: {hook_text}\n"

        f"ARCHETYPE GM DIRECTIVE: {arch_directive}"

    )



    import game_engine.prompt_layout as prompt_layout
    from mechanics.combat import is_in_combat, get_combat_prompt_and_schema
    
    mode = "combat" if is_in_combat(session) else "narrative"
    if mode == "combat":
        _, combat_schema = get_combat_prompt_and_schema(session, party)
        schema_to_use = json.dumps(combat_schema)
    else:
        schema_to_use = SCENE_SCHEMA



    from mechanics.social.physical_state import build_physical_prompt_block, init_default_physical_state

    from mechanics.system.time_engine import format_llm_time_context

    curr_day, curr_min, _ = db.get_session_time(session["id"])

    time_prompt_block = format_llm_time_context(curr_day, curr_min, scen_key)

    phys_anchor = build_physical_prompt_block(session, party, is_combat=is_in_combat(session), is_nsfw=is_nsfw_scenario(scenario))



    if arch_key == "hub_launchpad":

        choice_directive = (

            "OPENING CHOICE DIRECTIVE (HUB LAUNCHPAD):\n"

            "- Opening Narrative: Establish the lively hub atmosphere, distinct notable NPCs present, local rumors, and ambient opportunities.\n"

            "- Generate 4 diverse, character-tailored choices:\n"

            "  1. A clear forward action or onward departure heading toward the primary local rumor or regional destination.\n"

            "  2. Direct social engagement (speaking with a notable NPC present about current developments or rumors).\n"

            "  3. Environmental/information gathering (checking contract boards, scanning records, assessing the crowd).\n"

            "  4. A free roleplay/preparation action (stat: 'NONE', requirement: 0) such as checking gear, ordering drinks, or observing quietly."

        )

    elif arch_key == "in_media_res":

        choice_directive = (

            "OPENING CHOICE DIRECTIVE (IN MEDIA RES - HIGH TENSION CRISIS):\n"

            "- Opening Narrative: Plunge directly into the immediate high-stakes crisis with danger unfolding right now.\n"

            "- Generate 4 distinct tactical responses adapted to the character's class/skills:\n"

            "  1. Direct confrontation or decisive offensive counter-measure against the imminent threat.\n"

            "  2. Tactical defensive maneuver, barrier deployment, or safeguarding a vulnerable point/ally.\n"

            "  3. Environmental exploitation, repositioning, or agile flanking/evasion.\n"

            "  4. A rapid assessment or quick survival action tailored to the immediate predicament."

        )

    else:

        choice_directive = (

            "OPENING CHOICE DIRECTIVE (DELVE THRESHOLD - FRONTIER EXPLORATION):\n"

            "- Opening Narrative: Establish the character's arrival at this unique frontier site/ruin threshold, setting the sensory atmosphere and the mystery ahead.\n"

            "- Generate 4 distinct, immersive choices tailored to the environment and the character's specific class/abilities:\n"

            "  1. Direct breach or entry into the threshold tailored to the site's unique features.\n"

            "  2. Specialized environmental investigation or sensory/arcane/mechanical appraisal using character skills.\n"

            "  3. Tactical perimeter scouting, hazard bypass, or stealth pathing around the entryway.\n"

            "  4. A free orientation action (stat: 'NONE', requirement: 0) reviewing maps, steadying equipment, or securing the retreat route."

        )



    loc_anchor_line = f"STARTING LOCATION ANCHOR (Set `location` field to this or a matching tiered name): {suggested_loc}\n\n" if suggested_loc else ""



    temporal_mandate = (
        f"STRICT TEMPORAL CONSISTENCY MANDATE:\n"
        f"- Active starting clock time: {curr_min // 60:02d}:{curr_min % 60:02d} (Day {curr_day}).\n"
        f"- All narrative descriptions (lighting, sun position, ambient sounds, student and town activities) MUST STRICTLY conform to this active morning hour.\n"
        f"- STRICTLY FORBIDDEN: Do NOT narrate sunset, dusk, evening, twilight, or night when the clock indicates morning! Describe morning sunlight, students arriving, homeroom preparations, or morning routines.\n\n"
    )

    zone_0 = prompt_layout.build_static_core(mode, "opening")
    zone_1 = prompt_layout.build_session_zone(session)
    system_prompt = prompt_layout.assemble_system_prompt(zone_0, zone_1)

    user_prompt = (
        f"{temporal_mandate}"
        f"OPENING INCITING INCIDENT [{arch_title}]: {hook_text}\n"
        f"ARCHETYPE DIRECTIVE: {arch_directive}\n\n"
        f"{loc_anchor_line}"
        f"KNOWN WORLD:\n{game_engine._known_world_text(session['id'], suggested_loc or '', [], [])}\n\n"
        f"{time_prompt_block}\n"
        f"PHYSICAL CONTINUITY ANCHOR:\n{phys_anchor}\n\n"
        f"Begin adventure for {'party' if len(party) > 1 else 'character'}.\n\n"
        f"CHARACTER SHEET(S):\n{game_engine._party_sheet_text(party)}\n"
        f"{choice_directive}\n"
        f"Respond with JSON matching the required schema structure:\n{schema_to_use}"
    )
    result = await game_engine.call_llm_json(
        system_prompt, user_prompt,
        is_nsfw=is_nsfw_scenario(session.get("scenario")),
        response_model=OpeningScene
    )

    # Safety coercion: llm_client now returns dicts, but guard against Pydantic objects leaking through

    if getattr(result, "model_dump", None):

        result = result.model_dump(exclude_unset=False)

    if isinstance(result, dict) and is_location_engine_enabled(scen_key):

        s_nar = (result.get("narrative") or result.get("outcome_narrative") or "").strip()

        loc_to_reconcile = result.get("location") or suggested_loc

        result["location"] = game_engine.reconcile_movement_location(

            session["id"], "", loc_to_reconcile,

            action_text="Begin adventure", narrative=s_nar,

            scen_key=scen_key, char_name=first_char_name

        )

    res_deep = namegen.resolve_tokens_deep(result, scenario=scen_key)



    if isinstance(res_deep, dict):

        narrative = (res_deep.get("narrative") or res_deep.get("next_narrative") or res_deep.get("outcome_narrative") or "").strip()

        res_deep["narrative"] = game_engine.sanitize_comparative_cliches(narrative)

        init_default_physical_state(session["id"], party, scen_key, opening_scene=res_deep)



    # Persist LLM-generated Campaign End Goals

    end_goals = res_deep.get("campaign_end_goals") or []

    if end_goals and isinstance(end_goals, list):

        formatted_goals = []

        for idx, g in enumerate(end_goals, 1):

            if isinstance(g, dict):

                formatted_goals.append({

                    "id": g.get("id") or f"G{idx}",

                    "title": g.get("title", f"Campaign Goal {idx}"),

                    "description": g.get("description", ""),

                    "progress_pct": 0,

                    "status": "Active"

                })

        if formatted_goals:

            db.update_session_campaign_goals(session["id"], formatted_goals)



    # Persist the Chapter 1 Story Quest via dedicated story quest generator

    if not existing_sq:

        try:

            starting_hook_ctx = {

                "archetype": arch_key,

                "archetype_title": arch_title,

                "hook_text": hook_text,

                "suggested_location": suggested_loc,

                "opening_narrative": narrative[:500] if narrative else "",

                "scene_title": (res_deep.get("scene_title") or "").strip()

            }

            sq_data = await game_engine.generate_story_quest(session["id"], session, chapter_num=1, starting_hook_context=starting_hook_ctx)

            sq_title = sq_data.get("title") or "Story Quest #1: The Discovery"

            sq_archetype = sq_data.get("archetype") or "Story Quest"

            sq_objective = sq_data.get("objective") or "Explore the area, uncover local mysteries, and establish your footing."

            formatted_sub_objs = sq_data.get("sub_objectives") or []

            sub_waypoints = sq_data.get("sub_waypoints") or {}



            import uuid

            sq_id = f"SQ-{uuid.uuid4().hex[:8].upper()}"

            db.upsert_quest(

                session_id=session["id"],

                quest_id=sq_id,

                quest_type=sq_archetype,

                title=sq_title,

                objective=sq_objective,

                progress="Quest #1",

                current_clues="",

                status="Active",

                reward_xp=250,

                reward_gold=60,

                is_story_quest=1,

                clues_required=len(formatted_sub_objs),

                sub_objectives=formatted_sub_objs

            )



            # Persist waypoints for each sub-objective

            for so in formatted_sub_objs:

                so_id = so["id"]

                wps = sub_waypoints.get(so_id) or []

                if wps:

                    db.save_quest_waypoints(session_id=session["id"], quest_id=sq_id, waypoints=wps, sub_obj_id=so_id)

        except Exception as e:

            import logging

            logging.getLogger(__name__).warning("generate_story_quest for Chapter 1 failed: %s", e)



    if isinstance(res_deep, dict):

        res_deep = game_engine.sync_hostile_entities(res_deep, session)

        active_enemies = game_engine.get_active_enemies(session) or game_engine.get_active_enemies(res_deep)

        if active_enemies:

            from mechanics.narrative.choice_generator import generate_categorized_combat_actions

            cat = generate_categorized_combat_actions(

                party=party,

                monster=active_enemies[0],

                location=res_deep.get("location", session.get("current_location", "area")),

                scenario=scen_key

            )

            code_choices = [a["label"] for a in cat.get("attacks", [])] + \
                           [m["label"] for m in cat.get("magic", [])] + \
                           [t["label"] for t in cat.get("tactics", [])]

            if cat.get("flee"):

                code_choices.append(cat["flee"]["label"])

            if code_choices:
                res_deep["choices"] = code_choices
                res_deep["next_choices"] = code_choices
        else:
            op_choices = res_deep.get("choices") or []
            if not any("observe your surroundings" in str(c.get("label", "") if isinstance(c, dict) else c).lower() for c in op_choices):
                op_choices.append({
                    "label": "Observe your surroundings and inspect those present",
                    "stat": "FREE",
                    "requirement": 0,
                    "mp_cost": 0
                })
                res_deep["choices"] = op_choices
                res_deep["next_choices"] = op_choices

    return res_deep

async def classify_custom_action(session: dict, char: dict, inventory: list, action_text: str) -> dict:

    from mechanics.narrative.intent import classify_action_intent, is_free_ambient_action, IntentCategory, IntentContext

    cur_npcs = [game_engine._get_npc_name(n) for n in (session.get("current_npcs") or []) if n]

    from mechanics.world.mobility import get_session_dialogue_partners

    dp_list = get_session_dialogue_partners(session)

    ctx = IntentContext(

        dialogue_partner=dp_list[0] if dp_list else "",

        dialogue_partners=dp_list,

        current_zone=get_zone_location_name(session.get("current_location", "")),

        present_npcs=cur_npcs,

        scenario=session.get("scenario", "default")

    )

    parsed = classify_action_intent(action_text, ctx)



    # Fast-path 1: Free ambient exploration actions

    if is_free_ambient_action(parsed):

        return {

            "stat": "NONE",

            "requirement": 0,

            "mp_cost": 0,

            "action_category": parsed.category.value,

            "fast_path": True,

            "intent": parsed.category.value,

            "target_npc": parsed.target_entity or ""

        }



    # Fast-path 2: Social invitations, romantic confessions, companion recruitment

    if parsed.category in (IntentCategory.ROMANTIC_CONFESSION, IntentCategory.SOCIAL_INVITE, IntentCategory.PARTY_RECRUIT):

        return {

            "stat": "CHA",

            "requirement": 8,

            "mp_cost": 0,

            "action_category": parsed.category.value,

            "fast_path": True,

            "intent": parsed.category.value,

            "target_npc": parsed.target_entity or ""

        }



    # Fast-path 3: Affection touch

    if parsed.category == IntentCategory.AFFECTION_TOUCH:

        return {

            "stat": "CHA",

            "requirement": 6,

            "mp_cost": 0,

            "action_category": "affection",

            "fast_path": True,

            "intent": parsed.category.value,

            "target_npc": parsed.target_entity or ""

        }



    # Fast-path 4: Gift offering

    if parsed.category == IntentCategory.GIFT_OFFER:

        return {

            "stat": "NONE",

            "requirement": 0,

            "mp_cost": 0,

            "action_category": "gift",

            "fast_path": True,

            "intent": parsed.category.value,

            "target_npc": parsed.target_entity or ""

        }



    # Fast-path 5: Clue / evidence investigation

    if parsed.category == IntentCategory.INVESTIGATE_CLUE:

        return {

            "stat": "PER",

            "requirement": 7,

            "mp_cost": 0,

            "action_category": "investigation",

            "fast_path": True,

            "intent": parsed.category.value,

            "target_npc": parsed.target_entity or ""

        }



    # Fast-path 6: Stealth, lockpicking, pickpocketing

    if parsed.category == IntentCategory.STEALTH_COVERT:

        stat_choice = "INT" if parsed.sub_target == "lockpick" else "AGI"

        return {

            "stat": stat_choice,

            "requirement": 8,

            "mp_cost": 0,

            "action_category": "stealth",

            "fast_path": True,

            "intent": parsed.category.value,

            "target_npc": parsed.target_entity or ""

        }



    # Fast-path 7: Media capture (photo, video, selfie)

    if parsed.category == IntentCategory.MEDIA_CAPTURE:

        return {

            "stat": "NONE",

            "requirement": 0,

            "mp_cost": 0,

            "action_category": "media_capture",

            "fast_path": True,

            "intent": parsed.category.value,

            "target_npc": parsed.target_entity or ""

        }



    # Fall back to LLM for creative/combat/generic actions

    user_prompt = (

        f"KNOWN WORLD:\n{game_engine._known_world_text(session['id'], session.get('current_location', ''), session.get('nearby_enemies', []), session.get('current_npcs', []))}\n\n"

        f"CHARACTER SHEET:\n{game_engine._character_sheet_text(char, inventory)}\n\n"

        f"RECENT HISTORY:\n{game_engine._history_text(session['history'], session_id=session.get('id'))}\n\n"

        f"Custom action: \"{action_text}\"\n"

        f"Decide governing Attribute and requirement (2-12). If spell, set mp_cost.\n"

    )

    result: ActionClassification = await game_engine.call_llm_json(SYSTEM_PROMPT, user_prompt, temperature=0.4,

                                 max_tokens=800, retries=2, is_nsfw=is_nsfw_scenario(session.get("scenario")), use_utility=True, response_model=ActionClassification)

    

    # We dump it immediately because `classify_custom_action` returns a dict used by many places and mutates it

    res_dict = result.model_dump(exclude_unset=True)

    if res_dict.get("stat") not in VALID_STATS:

        res_dict["stat"] = "AGI"

    res_dict["requirement"] = max(1, min(20, int(res_dict.get("requirement", 6))))

    res_dict["mp_cost"] = max(0, int(res_dict.get("mp_cost", 0)))

    

    if res_dict.get("is_memory_recall") and res_dict.get("recall_query"):

        from db.memory import active_recall_search

        recall_results = active_recall_search(session["id"], res_dict["recall_query"])

        if recall_results:

            res_dict["_active_recall"] = recall_results

            

    return res_dict

async def generate_custom_starter_gear(char_class: str, class_description: str, scenario: str = "fantasy", gender: str = "Male", race: str = "Human", weapon_name: str = "") -> dict:

    """Generates a thematically appropriate starting equipment loadout for custom and wacky professions.



    For custom classes (including joke/satirical professions), calls the LLM with a detailed

    system prompt that understands comedic and out-of-place concepts and instructs it to fully

    commit to the theme.  Each LLM-returned item name is then passed through the mechanics

    engine (parse_equipment_metadata + serialize_item) to produce valid [ITEM_JSON] items with

    proper archetypes, Damage Thresholds, stat modifiers, and tags — exactly as if they had

    been generated by the standard equipment generators.



    Falls back gracefully to the keyword-based archetype profile generator if the LLM call

    fails or returns unusable data.

    """

    from mechanics.combat.items import generate_starter_equipment_loadout, _infer_class_archetype_profile

    from mechanics.combat.items.weapons import generate_random_equipment as gen_weapon

    from mechanics.combat.items.armors import generate_random_equipment as gen_armor

    from mechanics.combat.items.clothing import generate_random_clothing

    from mechanics.combat.items.headwear import generate_random_equipment as gen_headwear

    from mechanics.combat.items.gloves import generate_random_equipment as gen_gloves

    from mechanics.combat.items.shoes import generate_random_equipment as gen_shoes

    from mechanics.combat.items.shields import generate_random_equipment as gen_shield

    from mechanics.combat.items.accessories import generate_random_equipment as gen_acc

    from mechanics.combat.equipment import parse_equipment_metadata

    from mechanics.combat.items.envelope import serialize_item

    from scenario_data import is_nsfw_scenario



    # ── Build the LLM user prompt ─────────────────────────────────────────────

    gender_str = str(gender or "Male").strip()

    race_str = str(race or "Human").strip()

    is_nsfw = is_nsfw_scenario(scenario)



    from game_engine.core import CUSTOM_STARTER_GEAR_SYSTEM_PROMPT, CUSTOM_STARTER_GEAR_SCHEMA

    user_prompt = (

        f"Character Profession: {char_class}\n"

        f"Description: {class_description or '(no description provided)'}\n"

        f"Scenario/Setting: {scenario}\n"

        f"Gender: {gender_str}\n"

        f"Species: {race_str}\n\n"

        f"Schema:\n{CUSTOM_STARTER_GEAR_SCHEMA}"

    )



    llm_result = {}

    try:

        llm_result = await game_engine.call_llm_json(

            CUSTOM_STARTER_GEAR_SYSTEM_PROMPT,

            user_prompt,

            temperature=0.85,

            max_tokens=1200,

            is_nsfw=is_nsfw,

            use_utility=True,

        )

    except Exception as exc:

        log.warning("generate_custom_starter_gear LLM call failed (%s). Using archetype fallback.", exc)



    if not llm_result or not isinstance(llm_result, dict):

        # Full fallback: keyword-based archetype profile

        return generate_starter_equipment_loadout(

            scenario=scenario,

            char_class=char_class,

            gender=gender,

            race=race,

            weapon_name=weapon_name,

            tier=3,

        )



    # ── Convert LLM item names to proper [ITEM_JSON] game items ──────────────

    # Slot → (generator_fn, item_type_str)

    _SLOT_GENERATORS = {

        "Head":        (lambda name: gen_headwear(scenario=scenario, slot="Head", tier=3, archetype=None), "Headwear"),

        "Armor":       (lambda name: gen_armor(scenario=scenario, slot="Armor", tier=3, archetype=None), "Armor"),

        "Top":         (lambda name: generate_random_clothing(scenario=scenario, slot="Top", tier=3), "Clothing"),

        "Bottom":      (lambda name: generate_random_clothing(scenario=scenario, slot="Bottom", tier=3), "Clothing"),

        "Gloves":      (lambda name: gen_gloves(scenario=scenario, slot="Gloves", tier=3, archetype=None), "Gloves"),

        "Shoes":       (lambda name: gen_shoes(scenario=scenario, slot="Shoes", tier=3, archetype=None), "Shoes"),

        "Shield":      (lambda name: gen_shield(scenario=scenario, slot="Shield", tier=3, archetype=None), "Shield"),

        "Accessory 1": (lambda name: gen_acc(scenario=scenario, slot="Accessory 1", tier=3), "Accessory"),

        "Accessory 2": (lambda name: gen_acc(scenario=scenario, slot="Accessory 2", tier=3), "Accessory"),

    }



    from mechanics.combat.equipment import parse_equipment_metadata as _parse_meta

    from mechanics.combat.items.envelope import serialize_item as _ser



    loadout = {}

    is_male = gender_str.lower() == "male"

    is_tailless = race_str.lower() in ("human", "elf", "dwarf", "gnome", "halfling", "orc", "half-elf")



    for slot, (gen_fn, default_type) in _SLOT_GENERATORS.items():

        entry = llm_result.get(slot)

        if not entry or not isinstance(entry, dict):

            continue  # LLM said null or missing → skip slot



        llm_name = str(entry.get("name", "")).strip()

        llm_desc = str(entry.get("description", "")).strip()

        slot_cost = int(entry.get("slot_cost", 1))



        if not llm_name:

            continue



        # --- Gender guard for Bottom slot ---

        if is_male and slot == "Bottom":

            if "skirt" in llm_name.lower() or "dress" in llm_name.lower():

                llm_name = llm_name.replace("Skirt", "Trousers").replace("skirt", "trousers").replace("Dress", "Tunic").replace("dress", "tunic")



        # --- Tailless species guard ---

        if is_tailless and "tail-slotted" in llm_name.lower():

            llm_name = llm_name.replace("Tail-Slotted ", "").replace("tail-slotted ", "")



        # Generate a base item via the mechanics engine to get full stats/archetype

        try:

            base_item = gen_fn(llm_name)

        except Exception:

            base_item = None



        if base_item:

            # Override the generated name with the LLM's creative name

            base_meta = base_item.get("metadata", {})

            base_meta["name"] = llm_name

            if llm_desc:

                base_meta["description"] = llm_desc

            base_meta["tier"] = 3

            base_item["name"] = llm_name

            base_item["effect"] = _ser(base_meta)

            base_item["slot_cost"] = slot_cost

            base_item["metadata"] = base_meta

        else:

            # Last-resort: plain name-only item with heuristic metadata

            dummy = {"name": llm_name, "item_type": default_type, "slot": slot}

            meta = _parse_meta(dummy)

            meta["name"] = llm_name

            if llm_desc:

                meta["description"] = llm_desc

            meta["tier"] = 3

            meta["slot"] = slot

            meta["item_type"] = default_type

            base_item = {

                "name": llm_name,

                "item_type": default_type,

                "slot": slot,

                "effect": _ser(meta),

                "metadata": meta,

                "slot_cost": slot_cost,

            }



        loadout[slot] = base_item



    # If the LLM returned nothing at all (all nulls), fallback to archetype-based generator

    if not loadout:

        log.warning("generate_custom_starter_gear: LLM returned all-null slots. Using archetype fallback.")

        return generate_starter_equipment_loadout(

            scenario=scenario,

            char_class=char_class,

            gender=gender,

            race=race,

            weapon_name=weapon_name,

            tier=3,

        )



    # ── Generate Weapon slot manually ────────────────────────────────────────

    if weapon_name:

        weapon = gen_weapon(scenario=scenario, slot="Weapon", tier=3, name=weapon_name)

    else:

        weapon = gen_weapon(scenario=scenario, slot="Weapon", tier=3)

    loadout["Weapon"] = weapon



    return loadout



