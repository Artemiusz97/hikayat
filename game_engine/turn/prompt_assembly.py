from __future__ import annotations

import game_engine
from config import LLM_PASS2_TIMEOUT, LLM_STREAM_TOTAL_DEADLINE
from game_engine.core import uses_nsfw_model
from mechanics.combat import is_in_combat
from .generation import log
from .phase_state import PreTurnState, PromptAssemblyState
from models.llm_schemas import DeterministicCombatNarration, DeterministicTurnNarration


async def assemble_and_call_turn_llm(
    session: dict,
    party: list,
    actions: list,
    pre_state: PreTurnState,
    *,
    stream_callback=None,
) -> PromptAssemblyState:
    _in_aftercare_for_core = pre_state._in_aftercare_for_core
    _in_intimate_for_core = pre_state._in_intimate_for_core
    _we_snap = pre_state._we_snap
    actions_text = pre_state.actions_text
    active_quests_str = pre_state.active_quests_str
    active_recall_blocks = pre_state.active_recall_blocks
    ambush_monsters = pre_state.ambush_monsters
    ambush_triggered = pre_state.ambush_triggered
    budget = pre_state.budget
    caseboard_block = pre_state.caseboard_block
    cast_plan = pre_state.cast_plan
    dialogue_prompt_block = pre_state.dialogue_prompt_block
    directive_note = pre_state.directive_note
    effective_location = pre_state.effective_location
    fow_dossier_block = pre_state.fow_dossier_block
    has_exited_convo = pre_state.has_exited_convo
    hist_text = pre_state.hist_text
    mode = pre_state.mode
    new_partners = pre_state.new_partners
    phys_prompt_block = pre_state.phys_prompt_block
    import game_engine.prompt_layout as prompt_layout
    raw_scene_ctx = pre_state.raw_scene_ctx
    scene_loc = pre_state.scene_loc
    scene_npcs_for_prompt = pre_state.scene_npcs_for_prompt
    simultaneity_note = pre_state.simultaneity_note
    stage_info = pre_state.stage_info
    time_prompt_block = pre_state.time_prompt_block
    world_bundle = pre_state.world_bundle
    wp_block = pre_state.wp_block
    # --- DYNAMIC TOKEN BUDGETING ---
    trimmed_scene_ctx = budget.trim(raw_scene_ctx, "lore")
    quest_board_text = ""
    if not _in_intimate_for_core and not _in_aftercare_for_core:
        quest_board_text = "".join(
            f"{b}\n\n" for b in (budget.trim(wp_block, "quest"), budget.trim(caseboard_block, "caseboard")) if b
        )
        if quest_board_text:
            quest_board_text += "[CASEBOARD & WAYPOINT PRESENCE NOTE: NPCs named or referenced in clues, caseboard entries, or waypoints (e.g. clue sources, suspects, archivists) are background investigation records. They are NOT physically present in the current room unless explicitly listed in 'NPCs currently present'. NEVER narrate them acting, watching, or standing in this scene.]\n\n"
        if fow_dossier_block:
            quest_board_text += f"{budget.trim(fow_dossier_block, 'quest')}\n\n"

    trimmed_history = hist_text
    trimmed_dialogue = budget.trim(dialogue_prompt_block, "dialogue")

    active_recall_text = ""

    if active_recall_blocks:

        # Deduplicate and format

        unique_recalls = list(dict.fromkeys(active_recall_blocks))

        recall_lines = "\n".join(f"• {r}" for r in unique_recalls)

        active_recall_text = f"\n\n[PLAYER ACTIVE RECALL - The player explicitly searched their memory. You MUST weave these facts into your response]:\n{recall_lines}"

    ambush_req_note = ""
    if ambush_triggered and ambush_monsters:
        e_names = ", ".join(m["name"] for m in ambush_monsters if m.get("name"))
        p_names = ", ".join(c.get("name", "Hero") for c, _ in (party or []) if isinstance(c, dict) and c.get("name")) or "the player"
        pres_npcs = [
            game_engine._get_npc_name(n)
            for n in (session.get("current_npcs") or [])
            if game_engine._get_npc_name(n) and game_engine._get_npc_name(n).lower() != "none"
        ]
        react_who = f"{p_names} and {', '.join(pres_npcs)}" if pres_npcs else p_names
        ambush_req_note = (
            f"- MANDATORY ENEMY ENCOUNTER NARRATION: Hostile enemies ({e_names}) appear in this turn! "
            f"Your prose in `@@OUTCOME` and `@@NEXT` MUST explicitly name {e_names}, describe how they appeared/attacked, "
            f"and describe how {react_who} reacted to the encounter.\n"
        )
    else:
        ambush_req_note = (
            "- ENEMY ENCOUNTER CONSISTENCY: Whenever hostile enemies are present in `ENEMIES CURRENTLY NEARBY`, "
            "your narrative MUST explicitly describe how those enemies appeared in the scene and how the player and any present characters/NPCs react to the encounter.\n"
        )

    if any(w in actions_text.lower() for w in ("observe your surroundings", "inspect those present", "survey the room and present")):
        directive_note += (
            "\n[OBSERVATION DIRECTIVE]: The player is actively inspecting the room and characters. "
            "In your narrative, output a vivid Perception-based vignette detailing the immediate physical environment, "
            "hidden details, and the postures/expressions of present characters.\n"
        )

    if has_exited_convo:
        directive_note += (
            "\n[CONVERSATIONAL DEPARTURE & SCENE TRANSITION DIRECTIVE]:\n"
            "The player has explicitly concluded the conversation, stepped away, or left the conversation.\n"
            "- In `@@OUTCOME`, narrate only the immediate parting gesture or departure (e.g. nodding, thanking them, stepping away). "
            "EVERY character present in the scene MUST STOP talking with the player! DO NOT have any NPCs continue, reopen, or capture dialogue with the player this turn! DO NOT reopen the conversation!\n"
            "- In `@@NEXT`, transition the scene forward into open exploration, room atmosphere, or the player's next move. NO characters should be speaking to the player.\n"
            "- In `@@CHOICES`, generate OPEN EXPLORATION, room inspection, or travel choices. DO NOT generate active dialogue choices.\n"
        )

    # Check access gate prompt directive from stage_info
    if stage_info.get("access_gate", {}).get("prompt_directive"):
        directive_note += f"\n{stage_info['access_gate']['prompt_directive']}\n"

    # Urgent Schedule Departure State Machine & 3-Band Conversation Prompt Directive
    schedule_transition_choice = None
    schedule_stay_choice = None
    departing_for_schedule = []
    if (new_partners or has_exited_convo) and not _in_intimate_for_core and not is_in_combat(session):
        try:
            from mechanics.social.conversation_choices import (
                build_conversation_prompt_directive,
                evaluate_conversation_departure_turn,
            )
            dep_eval = evaluate_conversation_departure_turn(
                session=session,
                actions=actions,
                new_partners=new_partners,
                has_exited_convo=has_exited_convo,
                party=party,
                stage_info=stage_info,
            )
            if dep_eval.get("directive_note"):
                directive_note += dep_eval["directive_note"]
            departing_for_schedule = list(dep_eval.get("departing_for_schedule") or [])
            new_partners = list(dep_eval.get("active_partners") or [])
            if cast_plan is not None:
                cast_plan.dialogue_partners = [
                    p for p in cast_plan.dialogue_partners
                    if any(p.strip().lower() == np.strip().lower() for np in new_partners)
                ]
                for dep_rec in departing_for_schedule:
                    dep_nm = str(dep_rec.get("name") or "").strip()
                    if dep_nm and dep_nm not in cast_plan.departing_npcs:
                        cast_plan.departing_npcs.append(dep_nm)
            if new_partners:
                if isinstance(session.get("_dealt_social_seeds"), list) and session.get("_dealt_social_seeds"):
                    _valid_np_low = {str(np).strip().lower() for np in new_partners if str(np).strip()}
                    _kept_seeds = [
                        s for s in session["_dealt_social_seeds"]
                        if isinstance(s, dict) and str(s.get("target_npc") or "").strip().lower() in _valid_np_low
                    ]
                    if not _kept_seeds:
                        try:
                            from mechanics.social import deck as _core_deck
                            _kept_seeds = _core_deck.deal_social_deck_seeds(
                                session=session,
                                partners=new_partners,
                                party=party,
                                current_npcs=session.get("pre_turn_stage_npcs") or session.get("current_npcs") or [],
                                desired_count=5,
                            )
                        except Exception:
                            _kept_seeds = []
                    session["_dealt_social_seeds"] = _kept_seeds
                directive_note += build_conversation_prompt_directive(session, new_partners, party=party)
            else:
                session.pop("_dealt_social_seeds", None)
                dialogue_prompt_block = ""
                trimmed_dialogue = ""
        except Exception as _conv_dep_err:
            log.warning("Failed evaluating conversation departure state: %s", _conv_dep_err)

    # --- 4-Zone Prompt Caching Architecture ---
    enemies_list = session.get('nearby_enemies', [])
    enemies_str = ""
    if enemies_list:
        enemies_str = "\nENEMIES CURRENTLY NEARBY:\n" + "\n".join(
            game_engine._describe_tracked_entity(e) for e in enemies_list
        ) + "\n"

    if party and not session.get("lead_character_gender"):
        lead_c = party[0][0] if isinstance(party[0], (tuple, list)) else party[0]
        if isinstance(lead_c, dict):
            session["lead_character_gender"] = lead_c.get("gender", "male")

    zone_0 = prompt_layout.build_static_core(mode, "turn")
    zone_1 = prompt_layout.build_session_zone(session)
    zone_1b = prompt_layout.build_world_canon_zone(session, world=world_bundle)
    _we_nsfw = uses_nsfw_model(session.get("scenario"))
    _we_lang = str(session.get("narration_language") or session.get("language") or "en")
    from mechanics.world.world_events.formatting import format_macro_events_for_z2, format_rumors_for_z3
    _pa_realm_id = ""
    if session.get("id") and session.get("current_node_id"):
        try:
            from mechanics.world.locations.realms import get_node_realm_id
            _pa_realm_id = get_node_realm_id(int(session["id"]), str(session["current_node_id"]))
        except Exception:
            _pa_realm_id = ""
    macro_events_z2 = format_macro_events_for_z2(
        _we_snap, lang=_we_lang, is_nsfw_enabled=_we_nsfw, current_realm_id=_pa_realm_id
    )
    rumors_z3 = format_rumors_for_z3(
        _we_snap, lang=_we_lang, is_nsfw_enabled=_we_nsfw, current_location=str(scene_loc or ""), current_realm_id=_pa_realm_id
    )
    # Z2 ordered least -> most volatile; the clock changes every turn so it goes last.
    fresh_zone_2 = "\n".join(p for p in [
        f"CHARACTER SHEET(S):\n{game_engine._party_sheet_text(party)}",
        f"{prompt_layout.SCENE_CONTEXT_HEADER}\n{trimmed_scene_ctx}",
        enemies_str.strip(),
        f"PHYSICAL CONTINUITY ANCHOR:\n{phys_prompt_block}",
        macro_events_z2,
        time_prompt_block,
    ] if p)

    present_npc_names = [
        nm
        for nm in (game_engine._get_npc_name(n) for n in (scene_npcs_for_prompt or []))
        if nm and nm.lower() != "none"
    ]
    epoch_enemy_names = [
        nm
        for nm in (game_engine._get_npc_name(e) for e in (enemies_list or []))
        if nm and nm.lower() != "none"
    ]
    _hist_tail = list(session.get("history") or [])[-1:]
    _last_turn_summary = (
        game_engine._history_text(_hist_tail, session_id=session.get("id"))
        if _hist_tail
        else ""
    )
    zone_2, user_prompt_prefix, _next_prompt_epoch = prompt_layout.resolve_prompt_epoch(
        session=session,
        mode=mode,
        scene_loc=str(scene_loc or ""),
        party=party,
        present_npc_names=present_npc_names,
        fresh_zone_2=fresh_zone_2,
        phys_prompt_block=phys_prompt_block,
        time_prompt_block=time_prompt_block,
        active_quests_str=active_quests_str,
        quest_board_text=quest_board_text,
        rumors_z3=rumors_z3,
        trimmed_history=trimmed_history,
        active_recall_text=active_recall_text,
        last_turn_summary=_last_turn_summary,
        enemy_names=epoch_enemy_names,
        enemies_str=enemies_str,
    )

    user_prompt = (
        f"{user_prompt_prefix}"
        f"ACTIONS:\n{actions_text}\n{simultaneity_note}\n{directive_note}\n\n"
        f"{trimmed_dialogue}"
        f"{ambush_req_note}"
        f"{prompt_layout.build_closing_reminder(session)}"
    )

    final_system_prompt_list = prompt_layout.assemble_system_prompt(zone_0, zone_1, zone_1b, zone_2)
    log.debug("prompt zones %s sizes %s",
              prompt_layout.zone_fingerprints(zone_0, zone_1, zone_1b, zone_2),
              [len(z) for z in (zone_0, zone_1, zone_1b, zone_2)])

    is_nsfw_flag = uses_nsfw_model(session.get("scenario"))
    response_schema = DeterministicCombatNarration if mode == "combat" else DeterministicTurnNarration

    result = None
    try:
        import llm_client
        with llm_client.narration_sampling_context(session, is_nsfw=is_nsfw_flag):
            if stream_callback:
                result = await game_engine.call_llm_json_stream(
                    final_system_prompt_list, user_prompt,
                    on_narrative_token=stream_callback,
                    is_nsfw=is_nsfw_flag,
                    timeout=LLM_STREAM_TOTAL_DEADLINE,
                    response_model=response_schema,
                    system_zones=(zone_0, zone_1, zone_1b, zone_2),
                )
            else:
                result = await game_engine.call_llm_json(
                    final_system_prompt_list, user_prompt,
                    is_nsfw=is_nsfw_flag,
                    timeout=LLM_PASS2_TIMEOUT,
                    response_model=response_schema,
                    system_zones=(zone_0, zone_1, zone_1b, zone_2),
                )
    except Exception as llm_err:
        log.warning(
            "LLM generation pass failed during turn resolution (%s: %s). Activating deterministic fallback narration.",
            type(llm_err).__name__,
            llm_err,
        )
        result = {
            "is_fallback": True,
            "_is_fallback_narrative": True,
            "fallback_reason": "models_unavailable",
            "outcome_narrative": "",
            "next_narrative": "",
            "scene_title": session.get("scene_title") or "Continuing the Journey",
            "location": effective_location or session.get("current_location", ""),
            "choices": [],
            "next_choices": [],
        }
    return PromptAssemblyState(
        _next_prompt_epoch=_next_prompt_epoch,
        departing_for_schedule=departing_for_schedule,
        final_system_prompt_list=final_system_prompt_list,
        new_partners=new_partners,
        result=result,
        schedule_stay_choice=schedule_stay_choice,
        schedule_transition_choice=schedule_transition_choice,
        user_prompt=user_prompt,
    )
