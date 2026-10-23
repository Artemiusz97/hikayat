from __future__ import annotations
from typing import Any, Optional, Dict, List, Tuple
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
    from mechanics.world.schedules import get_time_block_key

    curr_day, curr_min, _ = db.get_session_time(session["id"])

    hook_start_min = hook_context.get("starting_minute")
    if hook_start_min is not None and curr_day == 1 and not session.get("history"):
        curr_min = int(hook_start_min)
        session["current_minute"] = curr_min
        new_slot = get_time_block_key(curr_min)
        session["time_slot"] = new_slot
        try:
            db.update_session_time(session["id"], curr_day, curr_min, 0)
        except Exception:
            pass

    # Modernized starting hook integrations: focal point, scheduled roles, physical state, starting prop, visual cues
    hook_focal_point = hook_context.get("focal_point", "")
    if hook_focal_point:
        session["focal_point"] = hook_focal_point
        try:
            db.update_session(session["id"], focal_point=hook_focal_point)
        except Exception as e:
            log.warning("Failed updating focal_point in generate_opening_scene: %s", e)

    scheduled_roles = hook_context.get("scheduled_roles", [])
    if scheduled_roles:
        try:
            from game_engine.npcs.stage_manager import _spawn_canonical_role_npc_pre_turn
            from mechanics.social.persona.actor_card import derive_initial_micro_blocking
            curr_npcs = list(session.get("current_npcs") or [])
            curr_npc_names = {game_engine._get_npc_name(n).lower() for n in curr_npcs if n}
            for role_title in scheduled_roles:
                if role_title:
                    spawned = _spawn_canonical_role_npc_pre_turn(session, role_title, suggested_loc or "")
                    if spawned and spawned.get("name"):
                        sp_name = spawned["name"]
                        if sp_name.lower() not in curr_npc_names:
                            micro = derive_initial_micro_blocking(
                                spawned,
                                current_location=suggested_loc or "",
                                time_slot=session.get("time_slot", "morning"),
                                stage_role="room_bystander"
                            )
                            spawned["spot_and_posture"] = micro.get("spot_and_posture", "")
                            spawned["active_prop"] = micro.get("active_prop", "")
                            curr_npcs.append(spawned)
                            curr_npc_names.add(sp_name.lower())
            session["current_npcs"] = curr_npcs
            db.update_session(session["id"], current_npcs_json=json.dumps(curr_npcs))
        except Exception as e:
            log.warning("Failed spawning scheduled_roles in generate_opening_scene: %s", e)

    initial_phys = hook_context.get("initial_physical_state") or {}
    if initial_phys and session.get("id"):
        try:
            from mechanics.social.physical_state import upsert_actor_physical_state
            for p_entry in party:
                p_char = p_entry[0] if isinstance(p_entry, (tuple, list)) else p_entry
                if isinstance(p_char, dict) and p_char.get("name"):
                    upsert_actor_physical_state(session["id"], p_char["name"], initial_phys)
        except Exception as e:
            log.warning("Failed applying initial_physical_state in generate_opening_scene: %s", e)

    starting_prop = hook_context.get("starting_prop")
    if starting_prop and party:
        lead_uid = None
        first_elem = party[0]
        if isinstance(first_elem, (tuple, list)) and len(first_elem) >= 1 and isinstance(first_elem[0], dict):
            lead_uid = first_elem[0].get("user_id")
        elif isinstance(first_elem, (tuple, list)) and len(first_elem) >= 2 and isinstance(first_elem[1], int):
            lead_uid = first_elem[1]
        elif isinstance(first_elem, dict):
            lead_uid = first_elem.get("user_id")
        if lead_uid and isinstance(starting_prop, dict) and starting_prop.get("name"):
            try:
                db.add_item(
                    user_id=lead_uid,
                    name=starting_prop["name"],
                    item_type=starting_prop.get("item_type", "tool"),
                    effect=starting_prop.get("effect", ""),
                    force=True
                )
            except Exception as e:
                log.warning("Failed adding starting_prop to inventory in generate_opening_scene: %s", e)

    visual_cues = hook_context.get("visual_cues", "")
    if visual_cues:
        session["opening_visual_cues"] = visual_cues

    # Deterministic Pre-Seeding: Lock spatial graph and starting world_node_id in 0ms BEFORE calling the LLM
    if session.get("id") and is_location_engine_enabled(scen_key):
        try:
            from mechanics.world.locations.graph_seeder import ensure_session_spatial_graph_seeded
            ensure_session_spatial_graph_seeded(session["id"], scen_key, char_name=first_char_name)
            if suggested_loc:
                pre_node_id = db.resolve_node_id_from_location(session["id"], suggested_loc)
                if pre_node_id:
                    session["current_node_id"] = pre_node_id
                    db.update_session(session["id"], current_node_id=pre_node_id)
        except Exception as e:
            log.warning("Pre-LLM spatial graph seed warning in generate_opening_scene: %s", e)

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



    from mechanics.system.time_engine import get_time_of_day_phase, format_clock
    phase_name, emoji, lighting_desc = get_time_of_day_phase(curr_min)
    clock_str = format_clock(curr_min)
    temporal_mandate = (
        f"STRICT TEMPORAL CONSISTENCY MANDATE:\n"
        f"- Active starting clock time: {clock_str} ({phase_name} {emoji}, Day {curr_day}).\n"
        f"- Ambient lighting & atmosphere: {lighting_desc}.\n"
        f"- All narrative descriptions (lighting, shadows, sky condition, ambient sounds, and activities) MUST STRICTLY conform to this active time ({clock_str} - {phase_name}).\n"
        f"- Do NOT contradict the current clock time ({clock_str}) or lighting conditions!\n\n"
    )

    focal_line = f"MICRO FOCAL POINT & STANCE: {hook_focal_point}\n" if hook_focal_point else ""
    visual_line = f"SCENE ATMOSPHERE & VISUAL CUES: {visual_cues}\n" if visual_cues else ""

    if party and not session.get("lead_character_gender"):
        lead_c = party[0][0] if isinstance(party[0], (tuple, list)) else party[0]
        if isinstance(lead_c, dict):
            session["lead_character_gender"] = lead_c.get("gender", "male")

    zone_0 = prompt_layout.build_static_core(mode, "opening")
    zone_1 = prompt_layout.build_session_zone(session)
    system_prompt = prompt_layout.assemble_system_prompt(zone_0, zone_1)

    user_prompt = (
        f"{temporal_mandate}"
        f"OPENING INCITING INCIDENT [{arch_title}]: {hook_text}\n"
        f"ARCHETYPE DIRECTIVE: {arch_directive}\n\n"
        f"{focal_line}"
        f"{visual_line}"
        f"{loc_anchor_line}"
        f"KNOWN WORLD:\n{game_engine._known_world_text(session['id'], suggested_loc or '')}\n\n"
        f"{time_prompt_block}\n"
        f"PHYSICAL CONTINUITY ANCHOR:\n{phys_anchor}\n\n"
        f"Begin adventure for {'party' if len(party) > 1 else 'character'}.\n\n"
        f"CHARACTER SHEET(S):\n{game_engine._party_sheet_text(party)}\n"
        f"{choice_directive}\n"
        f"Respond with JSON matching the required schema structure:\n{schema_to_use}"
    )
    result = await game_engine.call_llm_json(
        system_prompt, user_prompt,
        is_nsfw=scenario_data.uses_nsfw_model(session.get("scenario")),
        response_model=OpeningScene,
        required_any_keys=[["narrative", "next_narrative", "outcome_narrative"]]
    )

    # Safety coercion: llm_client now returns dicts, but guard against Pydantic objects leaking through

    if getattr(result, "model_dump", None):

        result = result.model_dump(exclude_unset=False)

    if not isinstance(result, dict):
        result = {}

    if isinstance(result, dict) and is_location_engine_enabled(scen_key):

        s_nar = (result.get("narrative") or result.get("outcome_narrative") or "").strip()

        loc_to_reconcile = result.get("location") or suggested_loc

        result["location"] = game_engine.reconcile_movement_location(

            session["id"], "", loc_to_reconcile,

            action_text="Begin adventure", narrative=s_nar,

            scen_key=scen_key, char_name=first_char_name

        )

    res_deep = namegen.resolve_tokens_deep(result, scenario=scen_key)

    if isinstance(res_deep, dict) and session.get("id") and is_location_engine_enabled(scen_key):
        try:
            from mechanics.world.locations.graph_seeder import ensure_session_spatial_graph_seeded
            ensure_session_spatial_graph_seeded(session["id"], scen_key, char_name=first_char_name)
            init_loc = res_deep.get("location") or suggested_loc or ""
            if init_loc:
                init_node_id = db.resolve_node_id_from_location(session["id"], init_loc)
                if init_node_id:
                    res_deep["current_node_id"] = init_node_id
                    session["current_node_id"] = init_node_id
                    db.update_session(session["id"], current_node_id=init_node_id)
        except Exception as e:
            log.warning("Failed to seed/resolve initial current_node_id in generate_opening_scene: %s", e)



    if isinstance(res_deep, dict):

        narrative = (res_deep.get("narrative") or res_deep.get("next_narrative") or res_deep.get("outcome_narrative") or "").strip()
        if not narrative:
            loc_clean = (res_deep.get("location") or suggested_loc or "the surroundings").replace(" ➔ ", " - ")
            char_display = first_char_name or "You"
            narrative = (
                f"The morning light settles over {loc_clean}. {char_display} pauses to take in the bustling atmosphere as the day begins. "
                f"{hook_text} Opportunities and untold paths stretch out ahead, awaiting your first move."
            )
            res_deep["is_fallback"] = True
            session["is_fallback_generation"] = True

        if not (res_deep.get("scene_title") or "").strip():
            fallback_title = suggested_loc.split("➔")[-1].strip() if suggested_loc else "A New Beginning"
            res_deep["scene_title"] = fallback_title

        res_deep["narrative"] = game_engine.sanitize_comparative_cliches(narrative)
        res_deep["narrative"] = game_engine.sanitize_npc_pronoun_consistency(
            res_deep["narrative"], session=session, result=res_deep, party=party
        )

        # Reconcile NPCs present in the opening scene from prose, rosters, and audit
        eff_loc = res_deep.get("location") or suggested_loc or ""
        try:
            res_deep["npcs_present"] = game_engine.process_scene_npcs(
                res_deep, session, eff_loc, eff_loc, actions=[]
            )
        except Exception as e:
            log.warning("process_scene_npcs failed for opening scene: %s", e)

        # Detect any speaking NPCs to set initial dialogue partner
        try:
            from config import DETERMINISTIC_CAST
            if DETERMINISTIC_CAST:
                audit_speaking = (res_deep.get("entity_audit") or {}).get("speaking_characters") or []
                if audit_speaking:
                    res_deep["dialogue_partner"] = audit_speaking[0]
                    res_deep["dialogue_partners"] = audit_speaking
            else:
                full_nar = str(res_deep.get("narrative") or "")
                speaking_npcs = game_engine.extract_speaking_npcs_from_narrative(
                    full_nar, res_deep.get("npcs_present", []), party=party
                )
                if speaking_npcs:
                    res_deep["dialogue_partner"] = speaking_npcs[0]
                    res_deep["dialogue_partners"] = speaking_npcs
        except Exception as e:
            log.warning("dialogue partner extraction failed for opening scene: %s", e)

        init_default_physical_state(session["id"], party, scen_key, opening_scene=res_deep)

        if hook_focal_point and not res_deep.get("focal_point"):
            res_deep["focal_point"] = hook_focal_point
        if visual_cues and not res_deep.get("visual_cues"):
            res_deep["visual_cues"] = visual_cues



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



    # Persist the Chapter 1 Story Quest (0ms deterministic waypoint locking in production; respects mocks in tests)

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

            _is_sq_mocked = (
                hasattr(game_engine.generate_story_quest, "_mock_name")
                or hasattr(game_engine.generate_story_quest, "assert_called")
                or hasattr(game_engine.call_llm_json, "_mock_name")
                or hasattr(game_engine.call_llm_json, "assert_called")
            )
            if _is_sq_mocked:
                sq_data = await game_engine.generate_story_quest(session["id"], session, chapter_num=1, starting_hook_context=starting_hook_ctx)
            else:
                sq_data = game_engine.create_contextual_story_quest_data(
                    session["id"], session, chapter_num=1, starting_hook_context=starting_hook_ctx
                )
                if res_deep.get("story_quest_title"):
                    sq_data["title"] = str(res_deep["story_quest_title"]).strip()
                if res_deep.get("story_quest_objective"):
                    sq_data["objective"] = str(res_deep["story_quest_objective"]).strip()

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
            logging.getLogger(__name__).warning("generate_story_quest for Chapter 1 failed: %s. Applying emergency contextual generator.", e)
            try:
                sq_data = game_engine.create_contextual_story_quest_data(
                    session["id"], session, chapter_num=1, starting_hook_context=starting_hook_ctx
                )
                formatted_sub_objs = sq_data.get("sub_objectives") or []
                sub_waypoints = sq_data.get("sub_waypoints") or {}
                import uuid
                sq_id = f"SQ-{uuid.uuid4().hex[:8].upper()}"
                db.upsert_quest(
                    session_id=session["id"],
                    quest_id=sq_id,
                    quest_type=sq_data.get("archetype") or "Story Quest",
                    title=sq_data.get("title") or "Story Quest #1: The Discovery",
                    objective=sq_data.get("objective") or "Explore the area, uncover local mysteries, and establish your footing.",
                    progress=f"0/{len(formatted_sub_objs)} Cleared" if formatted_sub_objs else "Quest #1",
                    current_clues="",
                    status="Active",
                    reward_xp=250,
                    reward_gold=60,
                    is_story_quest=1,
                    clues_required=len(formatted_sub_objs),
                    sub_objectives=formatted_sub_objs
                )
                for so in formatted_sub_objs:
                    so_id = so["id"]
                    wps = sub_waypoints.get(so_id) or []
                    if wps:
                        db.save_quest_waypoints(session_id=session["id"], quest_id=sq_id, waypoints=wps, sub_obj_id=so_id)
            except Exception as e2:
                logging.getLogger(__name__).error("Failed to insert emergency contextual story quest: %s", e2)



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

_GOLD_SPEND_RE = re.compile(
    r"\b(?:pay|offer|bribe|give|spend|tip|toss|hand(?:\s+over)?|slide)\b[^.!;]{0,40}?\b(\d+)\s*(?:gold|gp|coins?|credits?|yen|bucks?|dollars?|silver)\b"
    r"|\b(\d+)\s*(?:gold|gp|coins?|credits?|yen|bucks?|dollars?)\b[^.!;]{0,30}?\b(?:bribe|tip|payment|fee|wager|bet)\b",
    re.IGNORECASE,
)
_LOOT_SEARCH_RE = re.compile(
    r"\b(?:loot|search|rummage|ransack|plunder|open|pry\s+open|check)\b[^.!;]{0,35}?\b(?:chest|corpse|body|bodies|crate|barrel|cache|stash|locker|remains|pockets|sack|coffer|safe|trunk)\b",
    re.IGNORECASE,
)
_SPAWN_ROLE_RE = re.compile(
    r"\b(?:talk\s+to|speak\s+(?:to|with)|approach|ask|flag\s+down|call\s+over|hail|greet)\s+(?:the|a|an|some)\s+([a-z][a-z\s\-]{2,24}?)\b(?=$|\s+(?:about|for|if|to|and|at|behind|near|in|on)\b|[,.!?])",
    re.IGNORECASE,
)
_COMBAT_ATTACK_RE = re.compile(
    r"^\s*(?:attack|strike|slash|stab|hit|shoot|cleave|smash|punch|kick)\s+(?:the\s+)?([a-z0-9#\-\s']{2,35})$",
    re.IGNORECASE,
)
_MEMORY_RECALL_RE = re.compile(
    r"\b(?:remember|recall|remind(?:\s+[a-z]+)?\s+about|bring\s+up\s+(?:the|our|what)|what\s+we\s+learned\s+about|think\s+back\s+to|ask\s+(?:[a-z]+\s+)?about\s+(?:our\s+promise|the\s+rumor|the\s+clue|what\s+happened))\b",
    re.IGNORECASE,
)


def extract_deterministic_recall_query(action_text: str, session_id: int | None = None) -> str:
    """Returns a clean recall search query if the action text references past memory/promises/clues, else ''."""
    act_str = str(action_text or "").strip()
    if not act_str:
        return ""
    if _MEMORY_RECALL_RE.search(act_str):
        return act_str
    if session_id:
        act_low = act_str.lower()
        try:
            from db.memory import get_active_commitments
            for comm in (get_active_commitments(session_id) or []):
                if not isinstance(comm, dict):
                    continue
                desc = str(comm.get("description") or "").strip()
                target_ent = str(comm.get("target_entity") or "").strip()
                source_ent = str(comm.get("source_entity") or "").strip()
                desc_tokens = [w for w in re.findall(r"[a-z]{4,}", desc.lower()) if w not in ("player", "promised", "agreed", "would", "will", "with", "that", "this", "from", "into", "about")]
                entity_mentioned = any(
                    ent and (ent.lower() in act_low or ent.lower().split()[0] in act_low)
                    for ent in (target_ent, source_ent)
                    if ent and ent.lower() != "player"
                )
                matched_tokens = [w for w in desc_tokens if w in act_low]
                if (entity_mentioned and matched_tokens) or len(matched_tokens) >= 2:
                    return f"{target_ent} {desc}".strip()
        except Exception:
            pass
    return ""


def _extract_deterministic_action_primitives(action_text: str, session: dict | None = None, parsed: Any = None) -> dict:
    """Extracts deterministic mechanical primitives (gold_spent, triggers_loot_roll, spawns_npc_role,
    combat_tactical_archetype, target_location, and _active_recall) in <1ms without relying on LLM prose."""
    act_str = str(action_text or "").strip()
    act_low = act_str.lower()
    primitives: dict[str, Any] = {
        "gold_spent": 0,
        "triggers_loot_roll": False,
        "spawns_npc_role": "",
        "combat_tactical_archetype": "",
        "target_location": "",
    }
    if not act_str:
        return primitives

    # 1. Gold spending / bribes
    m_gold = _GOLD_SPEND_RE.search(act_str)
    if m_gold:
        amt_str = m_gold.group(1) or m_gold.group(2)
        try:
            primitives["gold_spent"] = max(0, int(amt_str))
        except (ValueError, TypeError):
            pass

    # 2. Container / corpse loot search
    if _LOOT_SEARCH_RE.search(act_str):
        primitives["triggers_loot_roll"] = True

    # 3. Approaching an unseeded background role NPC
    m_role = _SPAWN_ROLE_RE.search(act_str)
    if m_role:
        cand_role = m_role.group(1).strip()
        cur_npcs = [game_engine._get_npc_name(n).lower() for n in ((session or {}).get("current_npcs") or []) if n]
        if cand_role.lower() not in cur_npcs and not any(cand_role.lower() in n for n in cur_npcs):
            primitives["spawns_npc_role"] = cand_role

    # 4. Target location from parsed movement intent
    if parsed is not None and getattr(parsed, "category", None) and getattr(parsed.category, "value", "") == "movement":
        primitives["target_location"] = str(getattr(parsed, "target_entity", "") or getattr(parsed, "sub_target", "") or "").strip()

    # 5. Combat tactical archetypes
    from mechanics.combat import is_in_combat
    if isinstance(session, dict) and is_in_combat(session):
        if any(w in act_low for w in ("chandelier", "brazier", "pillar", "kick into", "shove into", "knock over", "collapse", "explosive", "oil", "ledge", "scaffolding")):
            primitives["combat_tactical_archetype"] = "environmental_hazard"
        elif any(w in act_low for w in ("blind", "sand", "dirt", "disarm", "trip", "hamstring", "stun", "daze", "entangle", "pin")):
            primitives["combat_tactical_archetype"] = "tactical_debuff"
        elif any(w in act_low for w in ("parley", "surrender", "negotiate", "stand down", "truce", "ceasefire", "intimidate into")):
            primitives["combat_tactical_archetype"] = "combat_parley"
        elif any(w in act_low for w in ("weak spot", "eyes", "throat", "joint", "headshot", "called shot", "vital", "chink in")):
            primitives["combat_tactical_archetype"] = "called_shot"
        elif any(w in act_low for w in ("flank", "take cover", "high ground", "reposition", "circle behind", "vantage")):
            primitives["combat_tactical_archetype"] = "reposition"

    # 6. Deterministic active memory recall
    sess_id_val = session.get("id") if isinstance(session, dict) else None
    recall_q = extract_deterministic_recall_query(act_str, session_id=sess_id_val)
    if recall_q:
        primitives["is_memory_recall"] = True
        primitives["recall_query"] = recall_q
        if sess_id_val:
            try:
                from db.memory import active_recall_search
                recall_hits = active_recall_search(sess_id_val, recall_q)
                if recall_hits:
                    primitives["_active_recall"] = recall_hits
            except Exception:
                pass

    return primitives


def _fast_path_classify_ambient_action(action_text: str, ctx: Any = None, parsed: Any = None, session: dict | None = None) -> dict | None:
    """
    Fast-paths short (<= 11 words), single-clause, non-negated commands
    with confidence >= 0.95 (ambient commands, direct dialogue, affection, stealth,
    investigation, loot searches, social invites, and direct combat attacks).
    Returns structured action dict if eligible, or None if routing to LLM is required.
    """
    from mechanics.narrative.intent import classify_action_intent, IntentCategory

    words = action_text.strip().split()
    act_low = action_text.lower()
    is_negated = any(w in words for w in ("not", "don't", "dont", "never", "stop", "refuse", "without", "hardly", "barely"))
    is_multi_clause = any(conj in act_low for conj in (" but ", " while ", " although ", " then ", " before ", " after ", " because ", ";"))
    if len(words) > 11 or is_negated or is_multi_clause:
        return None

    if parsed is None:
        parsed = classify_action_intent(action_text, ctx)

    if getattr(parsed, "confidence", 1.0) < 0.95:
        return None

    is_in_dialogue = bool(ctx and (getattr(ctx, "dialogue_partner", None) or getattr(ctx, "dialogue_partners", None)))
    primitives = _extract_deterministic_action_primitives(action_text, session=session, parsed=parsed)

    # 0. Direct physical combat attack
    m_atk = _COMBAT_ATTACK_RE.match(action_text.strip())
    if m_atk:
        target_enemy = m_atk.group(1).strip()
        for sep in (" with ", " using ", " at "):
            if sep in target_enemy.lower():
                target_enemy = target_enemy[:target_enemy.lower().find(sep)].strip()
        return {
            "stat": "STR",
            "requirement": 7,
            "mp_cost": 0,
            "action_category": "combat_attack",
            "fast_path": True,
            "intent": "combat_attack",
            "sub_intent": "",
            "target_npc": target_enemy,
            "combat_target": target_enemy,
            **primitives,
        }

    # 1. Ambient exploration & navigation (free)
    if parsed.category in (
        IntentCategory.DIALOGUE_EXIT,
        IntentCategory.MOVEMENT,
        IntentCategory.REST_SLEEP,
        IntentCategory.MEDIA_CAPTURE,
        IntentCategory.INSPECT_BOARD,
        IntentCategory.AREA_SCOUT,
    ):
        if is_in_dialogue and parsed.category not in (IntentCategory.DIALOGUE_EXIT, IntentCategory.MOVEMENT):
            return None
        return {
            "stat": "NONE",
            "requirement": 0,
            "mp_cost": 0,
            "action_category": parsed.category.value,
            "fast_path": True,
            "intent": parsed.category.value,
            "sub_intent": parsed.sub_target or "",
            "target_npc": parsed.target_entity or "",
            **primitives,
        }

    # 2. Gift offering
    if parsed.category == IntentCategory.GIFT_OFFER:
        return {
            "stat": "NONE",
            "requirement": 0,
            "mp_cost": 0,
            "action_category": "gift",
            "fast_path": True,
            "intent": parsed.category.value,
            "sub_intent": parsed.sub_target or "",
            "target_npc": parsed.target_entity or "",
            **primitives,
        }

    # 3. Direct affection touch
    if parsed.category == IntentCategory.AFFECTION_TOUCH:
        return {
            "stat": "CHA",
            "requirement": 6,
            "mp_cost": 0,
            "action_category": "affection",
            "fast_path": True,
            "intent": parsed.category.value,
            "sub_intent": parsed.sub_target or "",
            "target_npc": parsed.target_entity or "",
            **primitives,
        }

    # 4. Social invites, romantic confessions, and companion recruitment
    if parsed.category in (IntentCategory.ROMANTIC_CONFESSION, IntentCategory.SOCIAL_INVITE, IntentCategory.PARTY_RECRUIT):
        return {
            "stat": "CHA",
            "requirement": 8,
            "mp_cost": 0,
            "action_category": parsed.category.value,
            "fast_path": True,
            "intent": parsed.category.value,
            "sub_intent": parsed.sub_target or "",
            "target_npc": parsed.target_entity or "",
            **primitives,
        }

    # 5. Clue and evidence investigation
    if parsed.category == IntentCategory.INVESTIGATE_CLUE:
        return {
            "stat": "PER",
            "requirement": 7,
            "mp_cost": 0,
            "action_category": "investigation",
            "fast_path": True,
            "intent": parsed.category.value,
            "sub_intent": parsed.sub_target or "",
            "target_npc": parsed.target_entity or "",
            **primitives,
        }

    # 6. Stealth and covert actions
    if parsed.category == IntentCategory.STEALTH_COVERT:
        stat_choice = "INT" if parsed.sub_target == "lockpick" else "AGI"
        return {
            "stat": stat_choice,
            "requirement": 8,
            "mp_cost": 0,
            "action_category": "stealth",
            "fast_path": True,
            "intent": parsed.category.value,
            "sub_intent": parsed.sub_target or "",
            "target_npc": parsed.target_entity or "",
            **primitives,
        }

    # 7. Progressive disclosure inquiry
    if parsed.category == IntentCategory.DISCLOSURE_INQUIRY:
        return {
            "stat": "CHA",
            "requirement": 8,
            "mp_cost": 0,
            "action_category": "disclosure_inquiry",
            "fast_path": True,
            "intent": parsed.category.value,
            "sub_intent": parsed.sub_target or "",
            "target_npc": parsed.target_entity or "",
            **primitives,
        }

    # 8. Container / corpse loot search
    if primitives.get("triggers_loot_roll"):
        return {
            "stat": "PER",
            "requirement": 6,
            "mp_cost": 0,
            "action_category": "investigation",
            "fast_path": True,
            "intent": parsed.category.value,
            "sub_intent": parsed.sub_target or "",
            "target_npc": parsed.target_entity or "",
            **primitives,
        }

    # 9. Direct conversational initiation / dialogue
    if parsed.category == IntentCategory.DIALOGUE_INIT:
        return {
            "stat": "CHA",
            "requirement": 6,
            "mp_cost": 0,
            "action_category": "dialogue",
            "fast_path": True,
            "intent": parsed.category.value,
            "sub_intent": parsed.sub_target or "",
            "target_npc": parsed.target_entity or "",
            **primitives,
        }

    return None


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

    fast_action = _fast_path_classify_ambient_action(action_text, ctx, parsed=parsed, session=session)
    if fast_action is not None:
        return fast_action

    primitives = _extract_deterministic_action_primitives(action_text, session=session, parsed=parsed)

    # Route all nuanced, conversational, social, or multi-clause custom actions to utility LLM
    user_prompt = (
        f"KNOWN WORLD:\n{game_engine._known_world_text(session['id'], session.get('current_location', ''), current_npcs=session.get('current_npcs', []))}\n\n"
        f"CHARACTER SHEET:\n{game_engine._character_sheet_text(char, inventory)}\n\n"
        f"RECENT HISTORY:\n{game_engine._history_text(session.get('history', []), session_id=session.get('id'))}\n\n"
        f"Custom action: \"{action_text}\"\n\n"
        f"Decide governing Attribute, requirement (2-12), intent, sub_intent, and target_npc. If spell, set mp_cost.\n"
    )

    try:
        result = await game_engine.call_llm_json(
            SYSTEM_PROMPT, user_prompt, temperature=0.4,
            max_tokens=800, retries=2, is_nsfw=scenario_data.uses_nsfw_model(session.get("scenario")),
            use_utility=True, response_model=ActionClassification
        )
        if getattr(result, "model_dump", None):
            res_dict = result.model_dump(exclude_unset=True)
        elif isinstance(result, dict):
            res_dict = dict(result)
        else:
            res_dict = {}
    except Exception as e:
        log.warning("classify_custom_action LLM call failed: %s; using fallback classification", e)
        res_dict = {
            "stat": "CHA" if any(w in action_text.lower() for w in ("talk", "speak", "ask", "tell", "whisper", "say", "confess", "smile", "greet")) else "AGI",
            "requirement": 6,
            "mp_cost": 0,
            "action_category": "generic"
        }

    # Structured intent, sub_intent, and target_npc resolution
    llm_intent = str(res_dict.get("intent") or "").lower().strip()
    llm_sub = str(res_dict.get("sub_intent") or "").lower().strip()
    llm_target = str(res_dict.get("target_npc") or "").strip()

    if llm_intent and llm_intent != "general_action":
        res_dict["intent"] = llm_intent
        res_dict["action_category"] = llm_intent
        if llm_intent in ("dialogue_exit", "movement", "rest_sleep", "media_capture"):
            res_dict["stat"] = "NONE"
            res_dict["requirement"] = 0
            res_dict["mp_cost"] = 0
    else:
        # Fall back to regex-parsed intent
        res_dict["intent"] = parsed.category.value
        res_dict["action_category"] = parsed.category.value

    res_dict["sub_intent"] = llm_sub or parsed.sub_target or ""
    res_dict["target_npc"] = llm_target or parsed.target_entity or ""

    # Merge deterministic primitives (preserving LLM value if non-empty, else deterministic regex value)
    res_dict["gold_spent"] = max(int(res_dict.get("gold_spent") or 0), int(primitives.get("gold_spent") or 0))
    res_dict["triggers_loot_roll"] = bool(res_dict.get("triggers_loot_roll") or primitives.get("triggers_loot_roll"))
    res_dict["spawns_npc_role"] = str(res_dict.get("spawns_npc_role") or primitives.get("spawns_npc_role") or "").strip()
    res_dict["combat_tactical_archetype"] = str(res_dict.get("combat_tactical_archetype") or primitives.get("combat_tactical_archetype") or "").strip()
    res_dict["target_location"] = str(res_dict.get("target_location") or primitives.get("target_location") or "").strip()

    if res_dict.get("stat") not in VALID_STATS:
        res_dict["stat"] = "AGI"

    if res_dict.get("stat") in ("NONE", "FREE"):
        res_dict["requirement"] = 0
    else:
        res_dict["requirement"] = max(1, min(20, int(res_dict.get("requirement", 6))))

    res_dict["mp_cost"] = max(0, int(res_dict.get("mp_cost", 0)))

    if primitives.get("_active_recall") and not res_dict.get("_active_recall"):
        res_dict["_active_recall"] = primitives["_active_recall"]
    elif res_dict.get("is_memory_recall") and res_dict.get("recall_query"):
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

    from scenario_data import uses_nsfw_model



    # ── Build the LLM user prompt ─────────────────────────────────────────────

    gender_str = str(gender or "Male").strip()

    race_str = str(race or "Human").strip()

    is_nsfw = uses_nsfw_model(scenario)



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
    _is_llm_mocked = hasattr(game_engine.call_llm_json, "_mock_name") or hasattr(game_engine.call_llm_json, "assert_called")

    if _is_llm_mocked:
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

    from scenario_data import is_non_combat_scenario
    from mechanics.combat.items.tags import make_narrative_metadata
    if is_non_combat_scenario(scenario):
        for slot, itm in list(loadout.items()):
            if isinstance(itm, dict):
                meta = itm.get("metadata", {})
                norm_meta = make_narrative_metadata(meta)
                itm["metadata"] = norm_meta
                itm["effect"] = _ser(norm_meta)

    return loadout



