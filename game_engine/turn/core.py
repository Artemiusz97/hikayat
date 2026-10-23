from .generation import get_narrative_requirements, log
from .constants import *
from mechanics.world.locations import *
from mechanics.social.persona import *
from mechanics.narrative.intent import *
from .dialogue import _build_dialogue_prompt_block, _compute_dialogue_intent
from .prompts import _build_quest_and_bounty_directives, _build_player_actions_text, _build_history_context
from game_engine.turn_context import TurnContext
import json
import random
from config import LLM_PASS2_TIMEOUT
import scenario_data
from game_engine.core import SYSTEM_PROMPT, OUTCOME_SCHEMA, is_nsfw_scenario, uses_nsfw_model
import namegen
from mechanics.combat.merchant import merchant_prompt_note
import logging
import game_engine
import re
from models.llm_schemas import TurnOutcome, ActionClassification, OpeningScene, DeterministicTurnNarration, DeterministicCombatNarration


def _get_enemy_base_name(name: str) -> str:
    return re.sub(r'\s+(?:#?\d+|[A-Z])$', '', str(name or "").strip())


def _is_enemy_mentioned_in_narrative(enemy_name: str, narrative_text: str) -> bool:
    base = _get_enemy_base_name(enemy_name)
    if not base:
        return True
    nar_low = str(narrative_text or "").lower()
    base_low = base.lower()
    if base_low in nar_low:
        return True
    tokens = [w for w in re.split(r'[\s\-]+', base_low) if len(w) >= 4]
    if tokens:
        head_noun = tokens[-1]
        if re.search(rf'\b{re.escape(head_noun)}s?\b', nar_low):
            return True
    return False


def _format_enemy_with_article(name: str) -> str:
    base = _get_enemy_base_name(name)
    if not base:
        return "a hostile enemy"
    low = base.lower()
    if low.startswith(("the ", "a ", "an ")):
        return base
    article = "an" if low[0] in "aeiou" else "a"
    return f"{article} {base}"


def _join_natural(items: list[str]) -> str:
    clean = [str(x).strip() for x in items if str(x).strip()]
    if not clean:
        return ""
    if len(clean) == 1:
        return clean[0]
    if len(clean) == 2:
        return f"{clean[0]} and {clean[1]}"
    return f"{', '.join(clean[:-1])}, and {clean[-1]}"


def ensure_enemy_encounter_narrative(
    result: dict,
    session: dict,
    party: list,
    actions: list = None,
    pre_turn_enemy_names: set = None,
) -> tuple[dict, str]:
    """Guarantees that whenever an enemy is encountered on a turn (or active hostiles are present
    and completely omitted from the LLM prose), the narrative explicitly describes how the enemy
    appeared and how the player and any present characters/NPCs react to the encounter."""
    if not isinstance(result, dict):
        return result, ""
    if result.get("_combat_resolved_notice"):
        return result, ""

    raw_enemies = result.get("nearby_enemies")
    if raw_enemies is None:
        raw_enemies = session.get("nearby_enemies") or []
    active_enemies = [
        m for m in (raw_enemies or [])
        if isinstance(m, dict) and m.get("hp", 1) > 0 and m.get("name")
    ]
    if not active_enemies:
        return result, ""

    pre_names = {str(n).lower() for n in (pre_turn_enemy_names or set())}
    newly_spawned = [
        m for m in active_enemies
        if _get_enemy_base_name(m.get("name", "")).lower() not in pre_names
    ]

    outcome_nar = str(result.get("outcome_narrative") or "").strip()
    next_nar = str(result.get("next_narrative") or result.get("narrative") or "").strip()
    combined_nar = f"{outcome_nar}\n{next_nar}".strip()

    if newly_spawned:
        missing_enemies = [
            m for m in newly_spawned
            if not _is_enemy_mentioned_in_narrative(m.get("name", ""), combined_nar)
        ]
    else:
        any_mentioned = any(
            _is_enemy_mentioned_in_narrative(m.get("name", ""), combined_nar)
            for m in active_enemies
        )
        missing_enemies = list(active_enemies) if not any_mentioned else []

    party_names = []
    for entry in (party or []):
        c_obj = entry[0] if isinstance(entry, (tuple, list)) else entry
        if isinstance(c_obj, dict) and c_obj.get("name"):
            party_names.append(str(c_obj["name"]).strip())
    lead_player = party_names[0] if party_names else "The adventurer"
    other_players = party_names[1:]

    enemy_base_lowers = {_get_enemy_base_name(m.get("name", "")).lower() for m in active_enemies}
    player_lowers = {p.lower() for p in party_names}
    raw_npcs = result.get("npcs_present")
    if raw_npcs is None:
        raw_npcs = session.get("current_npcs") or []
    present_npc_names = []
    for n in (raw_npcs or []):
        n_name = game_engine._get_npc_name(n) if n else ""
        if not n_name or n_name.lower() == "none":
            continue
        if n_name.lower() in enemy_base_lowers or n_name.lower() in player_lowers:
            continue
        if n_name not in present_npc_names:
            present_npc_names.append(n_name)

    raw_loc = str(result.get("location") or session.get("current_location") or "the area").strip()
    loc_parts = [p.strip() for p in raw_loc.split("➔") if p.strip()]
    if len(loc_parts) >= 2:
        loc_display = loc_parts[1] if loc_parts[-1].lower() in ("main area", "entrance", "exterior", "interior") else loc_parts[-1]
    elif loc_parts:
        loc_display = loc_parts[0]
    else:
        loc_display = "the area"

    appended_paragraph = ""
    if missing_enemies:
        formatted_enemies = []
        seen_bases = set()
        for m in missing_enemies:
            b_name = _get_enemy_base_name(m.get("name", ""))
            if b_name.lower() not in seen_bases:
                seen_bases.add(b_name.lower())
                formatted_enemies.append(_format_enemy_with_article(b_name))
        enemy_list_str = _join_natural(formatted_enemies)
        is_plural_enemies = len(formatted_enemies) > 1
        threat_noun = "hostile figures emerge" if is_plural_enemies else "a hostile threat emerges"

        appearance_sentence = (
            f"Before another moment can pass at {loc_display}, the atmosphere shifts violently as {threat_noun} "
            f"from the surrounding approaches—{enemy_list_str} suddenly lunging into view to spring an ambush and cut off any easy retreat!"
        )

        if present_npc_names:
            npc_str = _join_natural(present_npc_names)
            npc_verb = (
                "tense sharply at the sudden ambush, calling out urgent warnings and shifting"
                if len(present_npc_names) > 1
                else "tenses sharply at the sudden ambush, calling out an urgent warning and shifting"
            )
            actor_str = _join_natural([lead_player] + other_players)
            actor_verb = (
                "immediately pivot toward the emerging danger and drop into combat-ready stances with weapons drawn"
                if other_players
                else "immediately pivots toward the emerging danger and drops into a combat-ready stance with weapon drawn"
            )
            reaction_sentence = (
                f"{actor_str} {actor_verb}, while {npc_str} {npc_verb} into a defensive position as the confrontation erupts."
            )
        elif other_players:
            actor_str = _join_natural([lead_player] + other_players)
            reaction_sentence = (
                f"{actor_str} immediately pivot toward the emerging danger, drawing their weapons and dropping into a tight defensive formation as the confrontation erupts."
            )
        else:
            reaction_sentence = (
                f"{lead_player} immediately pivots toward the emerging danger, drawing their weapon and dropping into a combat-ready stance as the confrontation erupts."
            )

        appended_paragraph = f"{appearance_sentence} {reaction_sentence}"
    elif newly_spawned and present_npc_names:
        # Enemies were named by the LLM, but verify present NPCs' reaction wasn't omitted
        nar_low = combined_nar.lower()
        unmentioned_npcs = [
            n for n in present_npc_names
            if n.lower() not in nar_low and not any(tok in nar_low for tok in n.lower().split() if len(tok) >= 4)
        ]
        if unmentioned_npcs:
            npc_str = _join_natural(unmentioned_npcs)
            npc_verb = "react" if len(unmentioned_npcs) > 1 else "reacts"
            appended_paragraph = (
                f"Beside {lead_player}, {npc_str} {npc_verb} immediately to the sudden emergence of the hostiles, "
                f"calling out a sharp warning and bracing in a defensive posture as battle is joined."
            )

    if appended_paragraph:
        if next_nar:
            result["next_narrative"] = f"{next_nar}\n\n{appended_paragraph}"
        else:
            result["next_narrative"] = appended_paragraph
        if result.get("narrative"):
            result["narrative"] = result["next_narrative"]

    return result, appended_paragraph


async def resolve_turn(session: dict, party: list, actions: list, stream_callback=None, is_retry: bool = False) -> TurnOutcome:
    import db
    from mechanics.system.time_engine import format_llm_time_context, calculate_action_time_cost, advance_time, apply_sleep_rest, is_sleep_action
    session_id_val = session.get('id')
    ctx = TurnContext(session_id_val, session)

    pre_turn_enemy_names = {
        _get_enemy_base_name(m.get("name", "")).lower()
        for m in (session.get("nearby_enemies") or [])
        if isinstance(m, dict) and m.get("hp", 1) > 0 and m.get("name")
    }

    actions_text = _build_player_actions_text(actions, session=session)

    # Pre-turn deterministic clock advancement
    _pre_turn_sleep_info = None
    _pre_turn_time_info = None
    scen_key = session.get("scenario", "fantasy") if isinstance(session, dict) else "fantasy"

    if not is_retry:
        if session_id_val:
            try:
                prev_day, prev_min, _ = db.get_session_time(session_id_val)
            except Exception:
                prev_day = int(session.get("current_day", 1) or 1)
                prev_min = int(session.get("current_minute", 480) or 480)
        else:
            prev_day = int(session.get("current_day", 1) or 1)
            prev_min = int(session.get("current_minute", 480) or 480)

        session["_prev_turn_day"] = prev_day
        session["_prev_turn_minute"] = prev_min

        party_uids = []
        for char in (party or []):
            if isinstance(char, dict) and "user_id" in char:
                party_uids.append(char["user_id"])
            elif isinstance(char, (tuple, list)) and char and isinstance(char[0], dict) and "user_id" in char[0]:
                party_uids.append(char[0]["user_id"])

        if session_id_val:
            is_sleep = actions and any(is_sleep_action(a.get("label", "") if isinstance(a, dict) else str(a)) for a in actions)
            if is_sleep:
                _pre_turn_sleep_info = apply_sleep_rest(session_id_val, party_uids, scen_key=scen_key)
                session["current_day"] = _pre_turn_sleep_info.get("new_day", prev_day)
                session["current_minute"] = _pre_turn_sleep_info.get("new_minute", prev_min)
            else:
                first_act = actions[0] if actions else {}
                from mechanics.world.mobility import get_session_dialogue_partners
                from mechanics.combat import is_in_combat
                is_dialogue_active = bool(get_session_dialogue_partners(session))
                is_combat_active = bool(is_in_combat(session))
                old_loc_val = session.get("current_location", "")

                # Preliminary destination check if moving
                from mechanics.world.locations import extract_movement_destination, get_zone_location_name
                prelim_dest_loc = old_loc_val
                if not is_combat_active and actions:
                    if isinstance(first_act, dict) and first_act.get("target_location"):
                        prelim_dest_loc = first_act["target_location"]
                    elif isinstance(first_act, dict) and first_act.get("target_node_id") and session_id_val:
                        from mechanics.world.locations.pathfinding import format_node_hierarchy
                        prelim_dest_loc = format_node_hierarchy(session_id_val, first_act["target_node_id"])
                    else:
                        act_label = actions[0].get("label", "") if isinstance(actions[0], dict) else str(actions[0])
                        p_zone = get_zone_location_name(old_loc_val) if old_loc_val else ""
                        dest_pair = extract_movement_destination(act_label, session_id_val, current_zone=p_zone, scen_key=scen_key)
                        if dest_pair:
                            prelim_dest_loc = f"{dest_pair[0]} ➔ {dest_pair[1]}"

                time_delta = calculate_action_time_cost(
                    first_act,
                    scen_key=scen_key,
                    old_loc=old_loc_val,
                    new_loc=prelim_dest_loc,
                    is_dialogue=is_dialogue_active,
                    is_combat=is_combat_active,
                    session_id=session_id_val,
                )
                _pre_turn_time_info = advance_time(session_id_val, time_delta, party_uids=party_uids)
                session["current_day"] = _pre_turn_time_info.get("new_day", prev_day)
                session["current_minute"] = _pre_turn_time_info.get("new_minute", prev_min)
        else:
            is_sleep = actions and any(is_sleep_action(a.get("label", "") if isinstance(a, dict) else str(a)) for a in actions)
            if is_sleep:
                session["current_day"] = prev_day + 1
                session["current_minute"] = 420
            else:
                first_act = actions[0] if actions else {}
                time_delta = calculate_action_time_cost(
                    first_act,
                    scen_key=scen_key,
                    old_loc=session.get("current_location", ""),
                    new_loc=session.get("current_location", ""),
                    is_dialogue=False,
                    is_combat=False,
                    session_id=0,
                )
                session["current_minute"] = prev_min + time_delta

    from game_engine.npcs import compute_pre_turn_stage
    stage_info = compute_pre_turn_stage(session, actions, party=party, ctx=ctx)
    new_partners = stage_info["new_partners"]
    has_exited_convo = stage_info["has_exited_convo"]
    effective_location = stage_info["effective_location"]
    pre_turn_stage_npcs = stage_info["stage_npcs"]
    movement_dest_str = stage_info["movement_dest_str"]

    from config import DETERMINISTIC_CAST
    from mechanics.combat import is_in_combat
    from game_engine.npcs.cast_planner import plan_pre_turn, render_stage_plan, apply_cast_events
    cast_plan = None
    if DETERMINISTIC_CAST:
        cast_plan = plan_pre_turn(
            session, party, actions, stage_info=stage_info, is_combat=bool(is_in_combat(session)), new_loc=effective_location
        )
        new_partners = cast_plan.dialogue_partners
        if cast_plan.has_exited_convo:
            has_exited_convo = True

    import db
    from mechanics.world.mobility import get_session_dialogue_partners
    from mechanics.social.physical_state import (
        build_physical_prompt_block,
        is_erotic_intimate_contact as _core_is_erotic,
        detect_intimate_disengagement as _core_is_disengage,
    )
    from mechanics.social.intimate_excitement import classify_intimate_act as _core_classify_act

    _pre_phys = (db.get_session_physical_state(session.get("id")) if session.get("id") else None) or session.get("physical_state") or {}
    _pre_ic_str = str(_pre_phys.get("intimate_contact", "") if isinstance(_pre_phys, dict) else "")
    _pre_act_str = " ".join(str(a.get("label", "") if isinstance(a, dict) else a) for a in (actions or []))
    _pre_act_ok = True
    for _pa in (actions or []):
        if isinstance(_pa, dict):
            _pchk = _pa.get("check")
            _ptier = getattr(_pchk, "tier", None) or (_pchk.get("tier") if isinstance(_pchk, dict) else None)
            if _pa.get("success") is False or _ptier in ("fail", "crit_fail"):
                _pre_act_ok = False
                break
    _cand_core_partners = list(new_partners or [])
    for _existing_dp in get_session_dialogue_partners(session):
        if _existing_dp and _existing_dp not in _cand_core_partners:
            _cand_core_partners.append(_existing_dp)
    if not _cand_core_partners:
        _cand_core_partners = ["Partner"]
    _initiating_erotic_act = False
    if _pre_act_ok and _pre_act_str:
        for _cp_cand in _cand_core_partners:
            if _core_classify_act(_pre_act_str, intimate_contact_str=_pre_ic_str, partner_name=_cp_cand).get("act_type", "none") not in ("none", "foreplay_nongenital"):
                _initiating_erotic_act = True
                break
    _in_intimate_for_core = (
        not _core_is_disengage(actions)
        and (_core_is_erotic(_pre_ic_str) or _initiating_erotic_act)
    )
    _in_aftercare_for_core = (not _core_is_disengage(actions)) and ("aftercare" in _pre_ic_str.lower())

    simultaneity_note = ""
    if len(actions) > 1:
        simultaneity_note = (
            "\nThese actions happened AT THE SAME TIME, not in sequence. Decide "
            "whether they synergize (e.g. a flanking attack plus a distraction "
            "compound for a better result), conflict/waste each other (e.g. one "
            "blocks the other's approach), or are simply independent -- and let "
            "that shape both the shared narrative and each character's individual "
            "hp_change/mp_change/etc in character_outcomes.\n"
        )

    import game_engine.prompt_layout as prompt_layout

    active_quests_str = ""
    if not _in_intimate_for_core and not _in_aftercare_for_core:
        story_quest_context, side_bounties_context = _build_quest_and_bounty_directives(session, ctx)
        if story_quest_context.strip():
            active_quests_str += f"### PRIMARY STORY QUEST\n{story_quest_context}\n\n"
        if side_bounties_context.strip():
            active_quests_str += f"### SECONDARY SIDE BOUNTIES\n{side_bounties_context}\n\n"
        if active_quests_str:
            active_quests_str += "[QUEST PRESENCE NOTE: Characters mentioned in the above quests or bounties are NOT necessarily in the current room. Do NOT include them in the scene or dialogue unless they are explicitly listed in `NPCs currently present` or actively introduced.]\n\n"

    from mechanics.combat import is_in_combat, precompute_combat_turn, reconcile_combat_results
    mode = "combat" if is_in_combat(session) else "narrative"
    precomputed = None
    if mode == "combat":
        precomputed = precompute_combat_turn(session, party, actions)

    from mechanics.system.memory.budget import DynamicTokenBudget
    budget = DynamicTokenBudget.from_session(session, party, actions)
    
    import asyncio
    asyncio.create_task(db.update_missing_lorebook_embeddings(session_id_val))
    
    hist_text, query_embedding = await _build_history_context(session, ctx, budget=budget)
    
    directive_note = ""
    if precomputed and precomputed.get("directive"):
        directive_note = f"\n{precomputed['directive']}\n"

    # Pre-turn stage directives (hybrid sublocations, schedule shifts, canonical role spawns, tension timers)
    if stage_info.get("stage_directives"):
        for sdir in stage_info["stage_directives"]:
            if sdir and sdir not in directive_note:
                directive_note += f"\n{sdir}\n"

    if DETERMINISTIC_CAST and cast_plan is not None:
        stage_plan_text = render_stage_plan(cast_plan)
        directive_note += f"\n{stage_plan_text}\n"

    # --- DETERMINISTIC PRE-TURN ENGINES (Python-First, 0 Arbiter LLM calls) ---
    from game_engine.state.core import resolve_pre_turn_vitals_and_resources
    pre_vitals_res = resolve_pre_turn_vitals_and_resources(session, party, actions)
    for p_dir in (pre_vitals_res.get("stage_directives") or pre_vitals_res.get("directives") or []):
        if p_dir and p_dir not in directive_note:
            directive_note += f"\n{p_dir}\n"

    from game_engine.state.social import resolve_pre_turn_social_and_disclosures
    pre_social_res = resolve_pre_turn_social_and_disclosures(
        session, party, actions, new_dialogue_partners=new_partners
    )
    for s_dir in (pre_social_res.get("directives") or []):
        if s_dir and s_dir not in directive_note:
            directive_note += f"\n{s_dir}\n"

    pre_intimate_res = None
    if _in_intimate_for_core:
        from mechanics.social.intimate_excitement import resolve_pre_turn_intimacy_and_clothing
        pre_intimate_res = resolve_pre_turn_intimacy_and_clothing(
            session, party, actions, new_partners=new_partners
        )
        for i_dir in (pre_intimate_res.get("directives") or []):
            if i_dir and i_dir not in directive_note:
                directive_note += f"\n{i_dir}\n"

    from game_engine.quests import resolve_pre_turn_quests_and_clues
    _old_loc_for_quests = session.get("current_location")
    if effective_location:
        session["current_location"] = effective_location
    pre_quest_res = resolve_pre_turn_quests_and_clues(session, party, actions)
    if _old_loc_for_quests:
        session["current_location"] = _old_loc_for_quests
    for q_dir in (pre_quest_res.get("directives") or []):
        if q_dir and q_dir not in directive_note:
            directive_note += f"\n{q_dir}\n"

    # in_dialogue_mode prevents duplicate stall directive injection — dialogue_prompt_block
    # is the single authoritative prompt section for dialogue stall notes.
    _in_dialogue_mode = bool(get_session_dialogue_partners(session))

    if not _in_intimate_for_core and not _in_aftercare_for_core:
        escalation_directives = game_engine.build_scene_escalation_and_consequence_directives(
            session, party, actions, ctx.story_quest, in_dialogue_mode=_in_dialogue_mode
        )
        if escalation_directives:
            directive_note += f"\n{escalation_directives}\n"

    # --- HYBRID ENCOUNTER ENGINE (5-10% chance in dangerous/non-combat locations) ---
    ambush_triggered = False
    ambush_monsters = []
    scen_key = session.get("scenario", "fantasy")
    if (
        not is_in_combat(session)
        and not is_retry
        and not _in_intimate_for_core
        and not _in_aftercare_for_core
        and scenario_data.is_mechanic_enabled(scen_key, "tactical_combat")
        and not is_hub_location(session.get("current_location", ""))
    ):
        if random.random() < 0.08:
            from mechanics.combat.enemies import generate_balanced_encounter
            party_dicts = [char for char, _ in party] if party else []
            cur_chapter = session.get("current_chapter", 1)
            new_monsters, xp_mult = generate_balanced_encounter(
                party_dicts, scen_key, session.get("current_location", "area"), cur_chapter,
                language=session.get("narration_language") or session.get("language", "en")
            )
            # Pre-inject them into session so they appear in prompt
            session["nearby_enemies"] = new_monsters
            ambush_triggered = True
            ambush_monsters = list(new_monsters)
            # Break peaceful 1-on-1 dialogue lock when an ambush interrupts the scene
            new_partners = []
            _in_dialogue_mode = False
            names = ", ".join(m["name"] for m in new_monsters if m.get("name"))
            party_names_str = ", ".join(
                c.get("name", "Hero")
                for c, _ in (party or [])
                if isinstance(c, dict) and c.get("name")
            ) or "the player"
            present_npc_names = [
                game_engine._get_npc_name(n)
                for n in (session.get("current_npcs") or [])
                if game_engine._get_npc_name(n) and game_engine._get_npc_name(n).lower() != "none"
            ]
            npc_react_clause = (
                f" and present characters ({', '.join(present_npc_names)})"
                if present_npc_names
                else ""
            )
            directive_note += (
                f"\n[MANDATORY AMBUSH DIRECTIVE]: Enemies ({names}) have suddenly ambushed the party! "
                f"You MUST narrate their sudden appearance and attack in `outcome_narrative` and `next_narrative`, "
                f"and explicitly describe how {party_names_str}{npc_react_clause} react to the encounter "
                f"(drawing weapons, shouting warnings, taking defensive stances). "
                f"DO NOT resolve the fight this turn; just spring the trap!\n"
            )



    movement_dest_str = ''
    # --- TRAVEL & TRANSIT DIRECTIVE ---

    if not is_in_combat(session):

        for a in actions:

            label = a.get("label", "")

            raw_curr = session.get("current_location", "")

            parsed_z = get_zone_location_name(raw_curr) if raw_curr else ""

            action_dest = extract_movement_destination(label, session["id"], current_zone=parsed_z, scen_key=scen_key)

            if action_dest:

                dest_z, dest_p = action_dest
                movement_dest_str = f'{dest_z} \u2794 {dest_p}'

                cur_loc = session.get("current_location", "")

                old_primary = get_primary_location_name(cur_loc)

                is_crit_fail = bool(a.get("check") and getattr(a["check"], "tier", "") == "crit_fail")

                if is_crit_fail:

                    directive_note += (

                        f"\n[TRAVEL COMPLICATION DIRECTIVE]: The party attempted to travel to [{dest_z} ➔ {dest_p}] but suffered a Critical Failure! "

                        f"Narrate a sudden catastrophe, ambush, or hazard blocking their journey on route.\n"

                    )

                else:

                    traveling_companions, left_behind_patrons = game_engine.classify_scene_npcs(session, actions, old_primary=old_primary, dest_primary=dest_p)

                    comp_names = [c["name"] for c in traveling_companions if c.get("name")]

                    patron_names = [p["name"] for p in left_behind_patrons if p.get("name")]

                    

                    comp_str = ", ".join(comp_names) if comp_names else "None (traveling solo)"

                    # Check if action or active quest specifies a target resident / station within dest_p
                    target_station_sub = None
                    target_resident_name = None
                    lbl_lower = (label or "").lower()

                    facility_residents = []
                    try:
                        facility_residents = db.get_school_characters_by_facility(session["id"], f"{dest_z} ➔ {dest_p}", limit=6)
                    except Exception:
                        facility_residents = []

                    # 1. Check if action mentions one of the facility residents
                    for fr in facility_residents:
                        fr_nm = (fr.get("name") or "").strip().lower()
                        if fr_nm and (fr_nm in lbl_lower or (len(fr_nm.split()) > 1 and fr_nm.split()[0] in lbl_lower)):
                            fr_fac = fr.get("primary_facility") or ""
                            if fr_fac:
                                _, _, fr_s = parse_tiered_location(fr_fac, scen_key, session_id=session["id"])
                                if fr_s and fr_s not in ("Main Area", ""):
                                    target_station_sub = fr_s
                                    target_resident_name = fr.get("name")
                                    break

                    # 2. Check active quest sub-objectives if not found yet
                    if not target_station_sub:
                        try:
                            with db.get_conn() as _c_conn:
                                q_rows = _c_conn.execute("SELECT sub_objectives_json FROM quests WHERE session_id=? AND status='Active'", (session["id"],)).fetchall()
                                for qr in q_rows:
                                    sub_objs = json.loads(qr["sub_objectives_json"] or "[]")
                                    for so in sub_objs:
                                        if not so.get("completed"):
                                            t_loc = so.get("target_location", "")
                                            t_npc = (so.get("target_npc") or "").strip().lower()
                                            if t_loc:
                                                qz, qp, qs = parse_tiered_location(t_loc, scen_key, session_id=session["id"])
                                                if qp.lower() == dest_p.lower() and qs and qs not in ("Main Area", ""):
                                                    if not t_npc or (t_npc in lbl_lower or (len(t_npc.split()) > 1 and t_npc.split()[0] in lbl_lower)):
                                                        target_station_sub = qs
                                                        target_resident_name = so.get("target_npc")
                                                        break
                                    if target_station_sub:
                                        break
                        except Exception:
                            pass

                    is_gated = bool(stage_info.get("access_gate", {}).get("gated"))
                    if not is_gated:
                        loc_prompt_target = target_station_sub or "[Specific Sub-Area]"
                        directive_note += (
                            f"\n[TRAVEL ARRIVAL & ESTABLISHMENT DEPARTURE DIRECTIVE]:\n"
                            f"- The party has departed [{old_primary}] and arrived at [{dest_z} ➔ {dest_p}].\n"
                            f"- Set `location` to '{dest_z} ➔ {dest_p} ➔ {loc_prompt_target}'.\n"
                        )
                    if target_resident_name and target_station_sub:
                        directive_note += f"- Target Resident: {target_resident_name} is stationed at {target_station_sub}.\n"
                    directive_note += f"- Companions traveling with the party: {comp_str}.\n"

                    if patron_names:
                        patron_str = ", ".join(patron_names)
                        directive_note += (
                            f"- Patrons left behind at {old_primary} (DO NOT NARRATE OR INCLUDE IN `npcs_present`): {patron_str}.\n"
                        )
                    directive_note += f"- Local environment: Introduce or focus on local NPCs native to {dest_p}.\n"

                    if facility_residents:
                        resident_lines = []
                        for fr in facility_residents:
                            fr_name = fr.get("name")
                            fr_role = fr.get("role") or ""
                            fr_gender = fr.get("gender") or ""
                            fr_fac = fr.get("primary_facility") or ""
                            _, _, fr_s = parse_tiered_location(fr_fac, scen_key, session_id=session["id"]) if fr_fac else ("", "", "")
                            station_txt = f" @ {fr_s}" if fr_s and fr_s not in ("Main Area", "") else ""
                            gender_txt = f", {fr_gender}" if fr_gender else ""
                            resident_lines.append(f"  * {fr_name} ({fr_role}{gender_txt}){station_txt}")
                        if resident_lines:
                            directive_note += (
                                f"- Canonical Facility Occupants stationed at {dest_p}:\n"
                                + "\n".join(resident_lines) + "\n"
                                f"- Roster & Presence Guidance: Focus interaction on the active scene characters. Other room occupants may be working quietly at their designated stations or away in class. Do not seat one character at another occupant's specific desk or station.\n"
                            )



                    # Check for pending phone appointments at this arrival destination

                    try:

                        from mechanics.world.waypoints import check_location_matches_waypoint

                        dest_full = f"{dest_z} ➔ {dest_p}"

                        pending_appts = ctx.pending_appointments

                        for appt in pending_appts:

                            appt_loc = appt.get("rendezvous_location", "")

                            npc_name = appt.get("npc_name", "")

                            if appt_loc and npc_name and check_location_matches_waypoint(dest_full, appt_loc):

                                directive_note += (

                                    f"\n[MANDATORY MEETUP RENDEZVOUS ON ARRIVAL ({npc_name})]:\n"

                                    f"- {npc_name} agreed via DM to meet here at {appt_loc} and is actively waiting for the player.\n"

                                    f"- This is a PRIVATE meeting/rendezvous between the player and {npc_name}. Uninvited peers or classmates from prior locations (such as homeroom or hallways) are NOT present and must NOT be mentioned in this scene.\n"

                                    f"- You MUST narrate {npc_name}'s greeting and presence in `outcome_narrative` and `next_narrative`.\n"

                                    f"- You MUST include {npc_name} in `present_named_characters`, `npcs_present`, and generate direct conversational choices with {npc_name} in `next_choices`.\n"

                                    f"- Set the location's sub-area to match the rendezvous if applicable (e.g. '{appt_loc}').\n"

                                )

                    except Exception:

                        pass

                break



    quest_prompt_req = (

        "- `quest_updates`: Update active quest status if relevant. Do NOT output clues during combat.\n"

        if is_in_combat(session)

        else "- `quest_updates`: For every active quest listed under PRIMARY STORY QUEST / SECONDARY SIDE BOUNTIES, include one entry. Set status=Completed if the objective was achieved, Failed if it failed, or Active if ongoing. Update `objective` and `current_clues` to reflect what happened this turn.\n"

    )



    session_for_phys = dict(session)
    if stage_info.get("is_movement"):
        session_for_phys["current_location"] = effective_location
        session_for_phys["current_npcs"] = pre_turn_stage_npcs
    phys_prompt_block = build_physical_prompt_block(
        session_for_phys, party,
        is_combat=is_in_combat(session),
        is_nsfw=is_nsfw_scenario(session.get("scenario")),
        actions=actions
    )




    dialogue_prompt_block = _build_dialogue_prompt_block(session, ctx, new_partners, party, actions)

    if session.get("id"):
        try:
            curr_day, curr_min, _ = db.get_session_time(session["id"])
        except Exception:
            curr_day, curr_min = int(session.get("current_day", 1) or 1), int(session.get("current_minute", 480) or 480)
    else:
        curr_day, curr_min = int(session.get("current_day", 1) or 1), int(session.get("current_minute", 480) or 480)

    time_prompt_block = format_llm_time_context(curr_day, curr_min, scen_key)



    # --- DYNAMIC TOKEN BUDGETING ---





    # Trim individual components to fit elastic budgets based on scene mode

    # KNOWN WORLD is split by volatility (see prompt_layout docstring):
    #   canon -> Z1b (cached; fixed cap, independent of scene mode)
    #   scene -> Z2  (per turn; "lore" budget)
    #   board -> Z3  (waypoints: "quest" budget, caseboard: "caseboard" budget)
    world_bundle = game_engine._load_known_world(session['id'])
    scene_loc = effective_location if effective_location else session.get('current_location', '')
    scene_npcs_for_prompt = pre_turn_stage_npcs if (stage_info.get("is_movement") or pre_turn_stage_npcs) else session.get('current_npcs', [])
    raw_scene_ctx = game_engine._scene_context_text(
        session['id'], scene_loc, current_npcs=scene_npcs_for_prompt,
        history_text=hist_text, world=world_bundle
    )
    trimmed_scene_ctx = budget.trim(raw_scene_ctx, "lore")
    quest_board_text = ""
    if not _in_intimate_for_core and not _in_aftercare_for_core:
        wp_block, caseboard_block = game_engine._quest_board_parts(
            session['id'], scene_loc, destination_location=movement_dest_str
        )
        quest_board_text = "".join(
            f"{b}\n\n" for b in (budget.trim(wp_block, "quest"), budget.trim(caseboard_block, "caseboard")) if b
        )
        if quest_board_text:
            quest_board_text += "[CASEBOARD & WAYPOINT PRESENCE NOTE: NPCs named or referenced in clues, caseboard entries, or waypoints (e.g. clue sources, suspects, archivists) are background investigation records. They are NOT physically present in the current room unless explicitly listed in 'NPCs currently present'. NEVER narrate them acting, watching, or standing in this scene.]\n\n"

    trimmed_history = budget.trim(hist_text, "history")

    trimmed_dialogue = budget.trim(dialogue_prompt_block, "dialogue")



    active_recall_blocks = []
    from game_engine.turn.generation import extract_deterministic_recall_query
    for a in actions:
        if isinstance(a, dict) and a.get("active_recall"):
            active_recall_blocks.extend(a["active_recall"])
        elif isinstance(a, dict) and session.get("id"):
            recall_q = extract_deterministic_recall_query(a.get("label", ""), session_id=session["id"])
            if recall_q:
                try:
                    from db.memory import active_recall_search
                    det_recalls = active_recall_search(session["id"], recall_q)
                    if det_recalls:
                        a["active_recall"] = det_recalls
                        active_recall_blocks.extend(det_recalls)
                except Exception:
                    pass

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
            f"Your prose in `outcome_narrative` and `next_narrative` MUST explicitly name {e_names}, describe how they appeared/attacked, "
            f"and describe how {react_who} reacted to the encounter.\n"
        )
    else:
        ambush_req_note = (
            "- ENEMY ENCOUNTER CONSISTENCY: Whenever hostile enemies are present in `nearby_enemies` or introduced in `new_entities`, "
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
            "- In `outcome_narrative`, narrate only the immediate parting gesture or departure (e.g. nodding, thanking them, stepping away). "
            "EVERY character present in the scene MUST STOP talking with the player! DO NOT have any NPCs continue, reopen, or capture dialogue with the player this turn! DO NOT reopen the conversation!\n"
            "- In `next_narrative`, transition the scene forward into open exploration, room atmosphere, or the player's next move. NO characters should be speaking to the player.\n"
            "- In `choices`, generate OPEN EXPLORATION, room inspection, or travel choices. DO NOT generate active dialogue choices.\n"
        )

    # Check access gate prompt directive from stage_info
    if stage_info.get("access_gate", {}).get("prompt_directive"):
        directive_note += f"\n{stage_info['access_gate']['prompt_directive']}\n"

    # Edge Case 6 & Issue 9: Mid-Conversation Schedule Transitions & Crossed Boundaries
    schedule_transition_choice = None
    schedule_stay_choice = None
    if new_partners and not _in_intimate_for_core and not is_in_combat(session):
        try:
            from mechanics.world.schedules import (
                is_schedule_transition_imminent,
                get_npc_scheduled_location,
                get_npc_scheduled_node_id,
                get_time_block_key
            )
            from mechanics.world.locations.access_gate import Phase2Choice

            curr_blk = get_time_block_key(curr_min)
            stay_overrides = list(session.get("stay_override_blocks") or [])

            # Check if current action is choosing to stay
            act_text_stay = " ".join(str(a.get("label", "") if isinstance(a, dict) else a).lower() for a in (actions or []))
            if "stay here a little longer" in act_text_stay:
                if curr_blk not in stay_overrides:
                    stay_overrides.append(curr_blk)
                    session["stay_override_blocks"] = stay_overrides
                    if session.get("id"):
                        try:
                            db.update_session(session["id"], extra={"stay_override_blocks": stay_overrides})
                        except Exception:
                            pass

            lead_p_name = new_partners[0]
            lead_c_match = next((c for c in (session.get("current_npcs") or []) if game_engine._get_npc_name(c) == lead_p_name), None)
            if not lead_c_match and session.get("id"):
                lead_c_match = next((c for c in (db.get_contacts(session["id"]) or []) if c.get("name") == lead_p_name), None)

            if lead_c_match and curr_blk not in stay_overrides:
                is_trans_imm, _, next_blk, mins_rem = is_schedule_transition_imminent(
                    curr_min, window_minutes=15, current_day=curr_day, scen_key=scen_key
                )
                # Check imminent window OR crossed boundary where NPC is scheduled elsewhere
                target_block = next_blk if (is_trans_imm and next_blk) else curr_blk
                target_min = (curr_min + mins_rem) if (is_trans_imm and mins_rem) else curr_min
                sched_loc = get_npc_scheduled_location(
                    lead_c_match, current_minute=target_min, current_day=curr_day,
                    scen_key=scen_key, time_slot=target_block, session_id=session.get("id")
                )
                if sched_loc and sched_loc.split("➔")[-1].strip().lower() not in scene_loc.lower():
                    dest_clean = sched_loc.split("➔")[-1].strip()
                    if is_trans_imm:
                        trans_desc = f"{lead_p_name}'s schedule shifts to {target_block.capitalize()} in {mins_rem} minutes (obligation at {dest_clean})."
                    else:
                        trans_desc = f"{lead_p_name}'s schedule routine requires them at {dest_clean} for {target_block.capitalize()}."
                    directive_note += (
                        f"\n[SCHEDULE OBLIGATION TRANSITION]: {trans_desc} "
                        f"{lead_p_name} should naturally mention this upcoming responsibility in their dialogue before wrapping up.\n"
                    )
                    schedule_transition_choice = Phase2Choice(f"Walk with {lead_p_name} to {dest_clean}", stat="NONE", requirement=0)
                    schedule_stay_choice = Phase2Choice(f"[CHA] Convince {lead_p_name} to stay here a little longer", stat="CHA", requirement=11)
        except Exception:
            pass

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
    # Z2 ordered least -> most volatile; the clock changes every turn so it goes last.
    zone_2 = "\n".join(p for p in [
        f"CHARACTER SHEET(S):\n{game_engine._party_sheet_text(party)}",
        f"{prompt_layout.SCENE_CONTEXT_HEADER}\n{trimmed_scene_ctx}",
        enemies_str.strip(),
        f"PHYSICAL CONTINUITY ANCHOR:\n{phys_prompt_block}",
        time_prompt_block,
    ] if p)
    
    user_prompt = (
        f"{active_quests_str}"
        f"{quest_board_text}"
        f"RECENT HISTORY:\n{trimmed_history}{active_recall_text}\n\n"
        f"ACTIONS:\n{actions_text}\n{simultaneity_note}\n{directive_note}\n\n"
        f"{trimmed_dialogue}"
        f"{ambush_req_note}"
        f"{prompt_layout.CLOSING_REMINDER}"
    )
    
    final_system_prompt_list = prompt_layout.assemble_system_prompt(zone_0, zone_1, zone_1b, zone_2)
    log.debug("prompt zones %s sizes %s",
              prompt_layout.zone_fingerprints(zone_0, zone_1, zone_1b, zone_2),
              [len(z) for z in (zone_0, zone_1, zone_1b, zone_2)])

    is_nsfw_flag = uses_nsfw_model(session.get("scenario"))
    response_schema = DeterministicCombatNarration if mode == "combat" else DeterministicTurnNarration

    result = None
    try:
        if stream_callback:
            result = await game_engine.call_llm_json_stream(
                final_system_prompt_list, user_prompt,
                on_narrative_token=stream_callback,
                is_nsfw=is_nsfw_flag,
                timeout=LLM_PASS2_TIMEOUT,
                response_model=response_schema
            )
        else:
            result = await game_engine.call_llm_json(
                final_system_prompt_list, user_prompt,
                is_nsfw=is_nsfw_flag,
                timeout=LLM_PASS2_TIMEOUT,
                response_model=response_schema
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

    # Safety coercion: llm_client now returns dicts, but guard against Pydantic objects leaking through
    if getattr(result, "model_dump", None):
        result = result.model_dump(exclude_unset=False)

    if isinstance(result, dict):
        result["_llm_system_prompt_list"] = final_system_prompt_list
        result = game_engine.sync_hostile_entities(result, session)

        if precomputed is not None:
            result = reconcile_combat_results(session, result, precomputed)




        # --- HYBRID STATUS EFFECT TIMER TICK ---

        from mechanics.combat import tick_status_timers

        for entry in party:

            char = entry[0] if isinstance(entry, (tuple, list)) else entry

            if isinstance(char, dict) and char.get("status_effects"):

                tick_status_timers(char)



        hostiles = session.get("nearby_enemies") or []

        surviving_hostiles = []

        dot_xp_gain = 0

        dot_gold_gain = 0

        dot_dead = []

        for monster in hostiles:

            if isinstance(monster, dict):

                if monster.get("status_effects"):

                    tick_status_timers(monster)

                if monster.get("hp", 1) > 0:

                    surviving_hostiles.append(monster)

                else:

                    dot_dead.append(monster.get("name", "Enemy"))

                    tier = monster.get("tier_rank", 1)

                    mult = monster.get("xp_multiplier", 1.0)

                    xp, gold = {1: (40, 15), 2: (75, 25), 3: (150, 60), 4: (260, 120), 5: (450, 250)}.get(tier, (75, 25))

                    dot_xp_gain += int(xp * mult)

                    dot_gold_gain += int(gold * mult)

            else:

                surviving_hostiles.append(monster)

        session["nearby_enemies"] = surviving_hostiles

        if dot_dead and isinstance(result, dict):

            c_outcomes = result.setdefault("character_outcomes", [])

            if not c_outcomes and party and party[0]:

                c_name = party[0][0].get("name", "Hero") if isinstance(party[0][0], dict) else "Hero"

                c_outcomes.append({"name": c_name, "hp_change": 0, "mp_change": 0, "xp_change": 0, "gold_change": 0})

            for co in c_outcomes:

                if isinstance(co, dict):

                    co["xp_change"] = co.get("xp_change", 0) + dot_xp_gain

                    co["gold_change"] = co.get("gold_change", 0) + dot_gold_gain

            

            result["dead_enemies"] = result.get("dead_enemies", []) + dot_dead

            result["dead_monsters"] = result.get("dead_monsters", []) + dot_dead

            result["nearby_enemies"] = surviving_hostiles

            

            if not surviving_hostiles:

                msg = f"⚔️ Victory! {', '.join(dot_dead)} succumbed to their wounds!\n**Rewards:** +{dot_xp_gain} XP, +{dot_gold_gain} Gold"

                if result.get("_combat_resolved_notice"):

                    if ", ".join(dot_dead) not in result["_combat_resolved_notice"]:

                        result["_combat_resolved_notice"] += "\n" + msg

                else:

                    result["_combat_resolved_notice"] = msg

                # Inject a loot choice

                loot_choice = {

                    "label": f"Search and loot the fallen enemies",

                    "stat": "FREE",

                    "requirement": 0,

                    "mp_cost": 0

                }

                c_list = result.get("next_choices") or result.get("choices") or []

                c_list = [loot_choice] + [c for c in c_list if not any(kw in (str(c.get("label", "")) if isinstance(c, dict) else str(c)).lower() for kw in ("attack", "strike with", "loot", "search the fallen"))][:3]

                result["next_choices"] = c_list

                result["choices"] = c_list

                # Despawn summons

                session["current_npcs"] = [npc for npc in session.get("current_npcs", []) if not npc.get("is_summon")]

                result["npcs_present"] = session["current_npcs"]



    import character_data

    from mechanics.social.relationships import safe_clamp_delta

    if isinstance(result, dict):
        result["_llm_system_prompt_list"] = final_system_prompt_list
        result["_llm_user_prompt"] = user_prompt

        # Determine if this turn is non-combat or a social interaction without combat
        scen_key = session.get("scenario", "fantasy") if session else "fantasy"
        is_non_combat_scen = scenario_data.is_non_combat_scenario(scen_key)
        active_enemies = (game_engine.get_active_enemies(result) or game_engine.get_active_enemies(session)) if result else []
        is_combat_turn = bool(active_enemies or (result and (result.get("_combat_log") or result.get("_enemy_attack_notice"))))

        from mechanics.social.intimate_excitement import is_intimate_action_label, matches_boundary
        from mechanics.social.physical_state import is_erotic_intimate_contact
        _sess_phys = (session.get("physical_state") if isinstance(session, dict) else None) or {}
        _res_phys_upd = (result.get("physical_updates") if isinstance(result, dict) else None) or {}
        _is_intimate_turn = (
            is_erotic_intimate_contact(str(_sess_phys.get("intimate_contact", "")))
            or is_erotic_intimate_contact(str(_res_phys_upd.get("intimate_contact", "")))
        )

        is_social_turn = not is_combat_turn and (
            _is_intimate_turn
            or any(
                str(a.get("action_category") or "").lower() in (
                    "dialogue", "disclosure_inquiry", "affection", "social_invite", "romantic_confession", "party_recruit", "social", "conversation", "chat", "flirt"
                ) or
                str(a.get("stat") or "").upper() == "CHA" or
                is_intimate_action_label(str(a.get("label") or "")) or
                bool(session.get("dialogue_partner") and matches_boundary(str(a.get("label") or "").lower(), ("talk", "speak", "ask", "tell", "say", "flirt", "tease", "confess", "whisper", "joke", "challenge", "inquire", "chat", "greet")))
                for a in (actions or [])
            )
        )
        # Merge deterministic pre-turn character outcomes (vitals, gold, loot)
        if pre_vitals_res and pre_vitals_res.get("character_outcomes"):
            res_cos = result.setdefault("character_outcomes", [])
            for pv_co in pre_vitals_res["character_outcomes"]:
                pv_name = str(pv_co.get("name", "")).strip().lower()
                existing_co = next((co for co in res_cos if isinstance(co, dict) and str(co.get("name", "")).strip().lower() == pv_name), None)
                if existing_co:
                    if pv_co.get("hp_change", 0) != 0 and existing_co.get("hp_change", 0) == 0:
                        existing_co["hp_change"] = pv_co["hp_change"]
                    if pv_co.get("gold_change", 0) != 0 and existing_co.get("gold_change", 0) == 0:
                        existing_co["gold_change"] = pv_co["gold_change"]
                    for itm in pv_co.get("items_gained", []):
                        if itm not in existing_co.setdefault("items_gained", []):
                            existing_co["items_gained"].append(itm)
                    for st in pv_co.get("status_effects", []):
                        if st not in existing_co.setdefault("status_effects", []):
                            existing_co["status_effects"].append(st)
                else:
                    res_cos.append(dict(pv_co))

        # Merge deterministic pre-turn social affinity deltas
        if pre_social_res and pre_social_res.get("affinity_deltas"):
            res_rus = result.setdefault("relationship_updates", [])
            for npc_n, aff_delta in pre_social_res["affinity_deltas"].items():
                existing_ru = next((ru for ru in res_rus if isinstance(ru, dict) and str(ru.get("npc_name", "")).strip().lower() == npc_n.strip().lower()), None)
                if existing_ru:
                    if aff_delta != 0 and existing_ru.get("delta_score", 0) == 0:
                        existing_ru["delta_score"] = aff_delta
                    existing_ru["_pre_turn_resolved"] = True
                else:
                    res_rus.append({"npc_name": npc_n, "delta_score": aff_delta, "_pre_turn_resolved": True})

        # Merge deterministic pre-turn quest progression
        if pre_quest_res:
            if pre_quest_res.get("completed_quests"):
                res_qus = result.setdefault("quest_updates", [])
                for comp_qid in pre_quest_res["completed_quests"]:
                    existing_qu = next((qu for qu in res_qus if isinstance(qu, dict) and str(qu.get("quest_id", qu.get("id", ""))) == str(comp_qid)), None)
                    if existing_qu:
                        existing_qu["status"] = "Completed"
                    else:
                        res_qus.append({"quest_id": comp_qid, "status": "Completed"})
            if pre_quest_res.get("reward_notices"):
                result["_quest_reward_notices"] = list(pre_quest_res["reward_notices"])
            if pre_quest_res.get("waypoint_notices"):
                result["_waypoint_notices"] = list(pre_quest_res["waypoint_notices"])
            if pre_quest_res.get("completed_sub_quests"):
                result["_completed_sub_quests"] = list(pre_quest_res["completed_sub_quests"])

        result["_pre_turn_vitals"] = pre_vitals_res
        result["_pre_turn_social"] = pre_social_res
        result["_pre_turn_quests"] = pre_quest_res
        if pre_intimate_res:
            result["_pre_turn_intimacy"] = pre_intimate_res
            if pre_intimate_res.get("physical_state"):
                result["_physical_state"] = pre_intimate_res["physical_state"]
            if pre_intimate_res.get("excitement_res"):
                result["_pre_turn_excitement_res"] = pre_intimate_res["excitement_res"]
            if pre_intimate_res.get("intimate_update") and not result.get("intimate_update"):
                result["intimate_update"] = pre_intimate_res["intimate_update"]
        if pre_vitals_res:
            if pre_vitals_res.get("merchant_encounter") and not result.get("merchant_encounter"):
                result["merchant_encounter"] = pre_vitals_res["merchant_encounter"]
            if pre_vitals_res.get("gifted_items"):
                result["_pre_turn_gifted"] = list(pre_vitals_res["gifted_items"])
            if pre_vitals_res.get("media_captured"):
                result["_pre_turn_media_captured"] = list(pre_vitals_res["media_captured"])
            if pre_vitals_res.get("consumed_items"):
                result["_pre_turn_consumed"] = list(pre_vitals_res["consumed_items"])
            if pre_vitals_res.get("loot_items_rolled"):
                result["_authorized_loot"] = list(pre_vitals_res["loot_items_rolled"])
        if pre_social_res and pre_social_res.get("faction_updates") and not result.get("faction_updates"):
            result["faction_updates"] = list(pre_social_res["faction_updates"])
        if pre_social_res and pre_social_res.get("faction_promotion_result") and not result.get("faction_promotion_result"):
            result["faction_promotion_result"] = pre_social_res["faction_promotion_result"]
        if pre_social_res and pre_social_res.get("fulfilled_commitments") and not result.get("fulfilled_commitments"):
            result["fulfilled_commitments"] = list(pre_social_res["fulfilled_commitments"])
        if pre_social_res and pre_social_res.get("broken_commitments") and not result.get("broken_commitments"):
            result["broken_commitments"] = list(pre_social_res["broken_commitments"])
        if pre_social_res and pre_social_res.get("created_commitments"):
            result["_created_commitments"] = list(pre_social_res["created_commitments"])

        if "character_outcomes" in result and isinstance(result["character_outcomes"], list):
            party_by_name = {char["name"].lower(): char for char, inv in party}
            filtered_outcomes = []
            has_failed_check = any(
                getattr(a.get("check"), "tier", "") in ("fail", "crit_fail") or
                (isinstance(a.get("check"), dict) and a["check"].get("tier") in ("fail", "crit_fail"))
                for a in (actions or [])
            )

            for outcome in result["character_outcomes"]:
                if isinstance(outcome, dict) and outcome.get("name"):
                    c_name = str(outcome["name"]).strip()
                    if c_name.lower() in party_by_name:
                        char = party_by_name[c_name.lower()]
                        if is_non_combat_scen or is_social_turn:
                            raw_hp = outcome.get("hp_change", 0)
                            if raw_hp and int(raw_hp) < 0:
                                log.info("[VitalsGuard] Suppressed non-combat HP damage (%s) for '%s' in non-combat/social scene.", raw_hp, c_name)
                                outcome["hp_change"] = 0
                            if outcome.get("temp_hp_change", 0) and int(outcome["temp_hp_change"]) < 0:
                                outcome["temp_hp_change"] = 0

                            act_mp_spent = sum(int(a.get("mp_spent") or 0) for a in (actions or []) if isinstance(a, dict) and (a.get("char") or {}).get("name", "").strip().lower() == c_name.lower())
                            raw_mp = outcome.get("mp_change", 0)
                            if raw_mp and int(raw_mp) < 0 and act_mp_spent == 0:
                                log.info("[VitalsGuard] Suppressed ungrounded non-combat MP drain (%s) for '%s' (no spell/mp spent in action).", raw_mp, c_name)
                                outcome["mp_change"] = 0

                            act_gold_spent = sum(int(a.get("gold_spent") or 0) for a in (actions or []) if isinstance(a, dict) and (a.get("char") or {}).get("name", "").strip().lower() == c_name.lower())
                            raw_gold = outcome.get("gold_change", 0)
                            if raw_gold and int(raw_gold) < 0 and act_gold_spent == 0:
                                act_texts = " ".join(str(a.get("label", "") + " " + a.get("text", "")).lower() for a in (actions or []) if isinstance(a, dict))
                                is_transaction = any(kw in act_texts for kw in ("buy", "purchase", "pay", "fee", "fine", "bribe", "tip", "rent", "order", "cost"))
                                if not is_transaction:
                                    log.info("[VitalsGuard] Suppressed ungrounded non-combat Gold deduction (%s) for '%s' (no transaction/purchase in action).", raw_gold, c_name)
                                    outcome["gold_change"] = 0

                        reconciled = character_data.reconcile_character_outcomes(char, outcome, is_non_combat=(is_non_combat_scen or is_social_turn))
                        outcome["hp_change"] = reconciled["actual_hp_delta"]
                        outcome["mp_change"] = reconciled["actual_mp_delta"]
                        outcome["gold_change"] = reconciled["actual_gold_delta"]
                        filtered_outcomes.append(outcome)
            result["character_outcomes"] = filtered_outcomes

            # Enforce that failed checks in social/non-combat scenes impact relationship affinity rather than physical HP
            if (is_non_combat_scen or is_social_turn) and has_failed_check:
                from mechanics.world.mobility import get_session_dialogue_partners
                from game_engine.matching import matches_keyword_boundary
                dp_list = get_session_dialogue_partners(session) if isinstance(session, dict) else []
                target_npc = None
                if actions:
                    for a in actions:
                        if a.get("target_npc"):
                            target_npc = a["target_npc"]
                            break
                        if a.get("combat_target"):
                            target_npc = a["combat_target"]
                            break
                        lbl = str(a.get("label") or a.get("text") or "").lower()
                        for dp in dp_list:
                            dp_low = dp.lower().strip()
                            dp_first = (dp_low.split() or [""])[0]
                            if matches_keyword_boundary(lbl, dp_low) or (len(dp_first) >= 3 and matches_keyword_boundary(lbl, dp_first)):
                                target_npc = dp
                                break
                        if target_npc:
                            break
                if not target_npc:
                    target_npc = dp_list[0] if dp_list else None

                if target_npc:
                    rel_updates = result.setdefault("relationship_updates", [])
                    target_ru = next(
                        (ru for ru in rel_updates if isinstance(ru, dict) and str(ru.get("npc_name", "")).strip().lower() == target_npc.lower()),
                        None
                    )
                    check_tier = "fail"
                    for a in (actions or []):
                        t = getattr(a.get("check"), "tier", None) or (a.get("check", {}).get("tier") if isinstance(a.get("check"), dict) else None)
                        if t in ("fail", "crit_fail"):
                            check_tier = t
                            break
                    penalty = -2 if check_tier == "crit_fail" else -1

                    if target_ru is not None:
                        if target_ru.get("delta_score", 0) >= 0:
                            target_ru["delta_score"] = penalty
                            log.info("[VitalsGuard] Converted failed check consequence for %s into relationship delta: %s", target_npc, penalty)
                    else:
                        lead_name = party[0][0].get("name", "Player") if party and party[0] else "Player"
                        rel_updates.append({
                            "npc_name": target_npc,
                            "delta_score": penalty,
                            "track": "platonic",
                            "memory_summary": f"Felt awkward or put off after {lead_name}'s misstep."
                        })
                        log.info("[VitalsGuard] Added affinity penalty (%s) for %s due to failed social check.", penalty, target_npc)



        if "relationship_updates" in result and isinstance(result["relationship_updates"], list):

            for ru in result["relationship_updates"]:

                if isinstance(ru, dict) and "delta_score" in ru:

                    ru["delta_score"] = safe_clamp_delta(ru["delta_score"], -20, 20)



        if "faction_updates" in result and isinstance(result["faction_updates"], list):

            for fu in result["faction_updates"]:

                if isinstance(fu, dict) and "delta_score" in fu:

                    fu["delta_score"] = safe_clamp_delta(fu["delta_score"], -20, 20)



        outcome_narrative = (

            result.get("outcome_narrative")

            or result.get("action_outcome")

            or result.get("resolution")

            or result.get("story")

            or result.get("scene_text")

            or result.get("description")

            or result.get("narrative")

            or result.get("text")

            or result.get("content")

            or result.get("next_narrative")

            or ""

        ).strip()

        

        next_narrative = (

            result.get("next_narrative")

            or result.get("narrative")

            or result.get("scene_text")

            or result.get("story")

            or result.get("description")

            or result.get("text")

            or result.get("content")

            or ""

        ).strip()



        if not outcome_narrative:
            a_label = actions[0].get("label", "acts") if actions else "acts"
            c_name = party[0][0].get("name", "The party") if party and party[0] else "The party"
            is_second_person = str(c_name).strip().lower() in ("you", "i")
            obs_keywords = ("observe", "inspect", "look", "examine", "survey", "perceive", "listen", "watch", "glance")
            if any(kw in a_label.lower() for kw in obs_keywords):
                take_verb = "take" if is_second_person else "takes"
                outcome_narrative = f"{c_name} {take_verb} a moment to carefully observe the surroundings and inspect those present."
            elif any(a_label.lower().startswith(pfx) for pfx in ("i travel to ", "travel to ", "i head to ", "head to ", "i walk to ", "walk to ")):
                dest_clean = a_label
                for pfx in ("i travel to ", "travel to ", "i head to ", "head to ", "i walk to ", "walk to "):
                    if a_label.lower().startswith(pfx):
                        dest_clean = a_label[len(pfx):].strip().rstrip(".")
                        break
                travel_verb = "travel" if is_second_person else "travels"
                outcome_narrative = f"{c_name} {travel_verb} to {dest_clean}."
            else:
                act_verb = "act" if is_second_person else "acts"
                outcome_narrative = f"{c_name} {act_verb} with deliberate intent: {a_label}."
            result["is_fallback"] = True
            result["_is_fallback_narrative"] = True



        if not next_narrative or next_narrative == outcome_narrative:

            curr_loc = session.get("current_location", "the area")

            lead_npc = next((game_engine._get_npc_name(n) for n in (session.get("current_npcs") or []) if n), None)

            npc_mention = f" beside {lead_npc}" if lead_npc else ""

            next_narrative = f"The atmosphere settles around {curr_loc}{npc_mention} as the immediate action resolves. The surrounding area remains active with subtle movement and tension, awaiting the party's next move."

            result["is_fallback"] = True

            result["_is_fallback_narrative"] = True



        result["outcome_narrative"] = outcome_narrative

        result["next_narrative"] = next_narrative



    result = namegen.resolve_tokens_deep(result, scenario=scen_key)

    game_engine._sanitize_outcome_person_names(result, session["id"], scen_key)

    if isinstance(result, dict) and is_location_engine_enabled(scen_key):
        old_loc = session.get("current_location", "")
        import config
        curr_nid = session.get("current_node_id") or (db.resolve_node_id_from_location(session["id"], old_loc) if session.get("id") else None)
        has_graph = bool(curr_nid)
        if stage_info.get("is_movement"):
            new_loc = effective_location or old_loc
        elif getattr(config, "DETERMINISTIC_MOVEMENT", True) and has_graph and "cast_events" in result:
            new_loc = old_loc
        else:
            new_loc = result.get("location") or old_loc
        new_node_id = stage_info.get("effective_node_id") or (db.resolve_node_id_from_location(session["id"], new_loc) if session.get("id") and new_loc else None) or session.get("current_node_id")
        focal_point = stage_info.get("focal_point") if stage_info.get("focal_point") is not None else result.get("focal_point")

        result["location"] = new_loc
        result["current_node_id"] = new_node_id
        if new_loc != old_loc:
            staged_seed = [dict(n) if isinstance(n, dict) else {"name": str(n)} for n in (result.get("npcs_present") or [])]
        else:
            staged_seed = [dict(n) if isinstance(n, dict) else {"name": str(n)} for n in (pre_turn_stage_npcs or result.get("npcs_present") or [])]
        try:
            result["npcs_present"] = game_engine.process_scene_npcs(
                result,
                session,
                new_loc=new_loc,
                old_loc=old_loc,
                actions=actions,
                staged_npcs=staged_seed,
                party=party
            )
        except Exception:
            result["npcs_present"] = staged_seed
        session["current_location"] = new_loc
        if new_node_id:
            session["current_node_id"] = new_node_id

        # Rendezvous Convergence on Arrival
        if session.get("id") and new_loc:
            try:
                from mechanics.world.waypoints import check_location_matches_waypoint
                active_appts = db.get_active_rendezvous_appointments(session["id"])
                for appt in active_appts:
                    appt_loc = appt.get("rendezvous_location", "")
                    appt_node = appt.get("target_node_id", "")
                    is_at_appt = False
                    if appt_node and new_node_id:
                        is_at_appt = db.is_descendant_of(session["id"], new_node_id, appt_node)
                    if not is_at_appt and appt_loc:
                        is_at_appt = check_location_matches_waypoint(new_loc, appt_loc) or check_location_matches_waypoint(appt_loc, new_loc)
                    if is_at_appt:
                        db.update_phone_appointment_status(session["id"], appt["npc_id"], "completed")
                        a_name = appt.get("npc_name", "")
                        if a_name:
                            if not any(game_engine.is_dialogue_partner(a_name, [game_engine._get_npc_name(n)]) for n in result["npcs_present"]):
                                result["npcs_present"].append({"name": a_name, "role": "Rendezvous Partner", "status_effects": ["Present"]})
                            if a_name not in new_partners:
                                new_partners.append(a_name)
                            has_exited_convo = False
            except Exception:
                pass

        if DETERMINISTIC_CAST and cast_plan is not None and "cast_events" in result:
            cast_plan.present_npcs = list(result.get("npcs_present") or [])
            raw_cast_events = result.get("cast_events") or []
            final_plan, cast_rejections = apply_cast_events(
                cast_plan, raw_cast_events, session=session, party=party, stage_info=stage_info
            )
            new_partners = final_plan.dialogue_partners
            result["_cast_rejections"] = cast_rejections
            if has_exited_convo or cast_plan.has_exited_convo:
                new_partners = []
                if result.get("npcs_present"):
                    for n in result["npcs_present"]:
                        if isinstance(n, dict):
                            if n.get("stage_role") == "active_partner":
                                n["stage_role"] = "room_bystander"
                            if n.get("attention_ring") == "ring_1_partner":
                                n["attention_ring"] = "ring_3_bystander"
                            if isinstance(n.get("micro_blocking"), dict) and n["micro_blocking"].get("proximity") == "conversational_distance":
                                n["micro_blocking"]["proximity"] = "across_room"
            # Synchronize authoritative room attendance
            result["npcs_present"] = final_plan.present_npcs
            session["current_npcs"] = final_plan.present_npcs
        else:
            # Legacy Ring-2 Attentive Peer Chime-In Check (fallback when DETERMINISTIC_CAST is False)
            if result.get("npcs_present"):
                s_nar = (result.get("next_narrative") or result.get("narrative") or result.get("outcome_narrative") or "").strip()
                full_nar = f"{outcome_narrative}\n{next_narrative}\n{s_nar}"
                pres_names = [game_engine._get_npc_name(n) for n in result["npcs_present"] if game_engine._get_npc_name(n)]
                retained_partners = [p for p in new_partners if any(game_engine.is_dialogue_partner(p, [pn]) for pn in pres_names)] if not has_exited_convo else []
                lead_p_name = party[0][0].get("name") if party and party[0] and isinstance(party[0][0], dict) else None
                speaking_npcs = game_engine.extract_speaking_npcs_from_narrative(
                    full_nar, result["npcs_present"], party=party, player_name=lead_p_name
                )
                if not speaking_npcs and not has_exited_convo:
                    from mechanics.world.mobility import is_rendezvous_target
                    for n in result["npcs_present"]:
                        n_nm = game_engine._get_npc_name(n)
                        if n_nm and n_nm.lower() != "none" and is_rendezvous_target(n_nm, actions=actions, session_id=session.get("id"), new_loc=new_loc):
                            speaking_npcs.append(n_nm)

                same_primary = bool(
                    old_loc == new_loc
                    or (
                        get_primary_location_name(old_loc)
                        and get_primary_location_name(old_loc).lower() == get_primary_location_name(new_loc).lower()
                    )
                )
                if has_exited_convo:
                    new_partners = []
                    if result.get("npcs_present"):
                        for n in result["npcs_present"]:
                            if isinstance(n, dict):
                                if n.get("stage_role") == "active_partner":
                                    n["stage_role"] = "room_bystander"
                                if n.get("attention_ring") == "ring_1_partner":
                                    n["attention_ring"] = "ring_3_bystander"
                                if isinstance(n.get("micro_blocking"), dict) and n["micro_blocking"].get("proximity") == "conversational_distance":
                                    n["micro_blocking"]["proximity"] = "across_room"
                else:
                    merged = list(retained_partners) if same_primary else []
                    for sn in speaking_npcs:
                        if not any(game_engine.is_dialogue_partner(sn, [m]) for m in merged):
                            if game_engine.evaluate_scene_attention_transition(
                                sn,
                                retained_partners=retained_partners,
                                actions=actions,
                                narrative=full_nar,
                                session=session,
                                party=party,
                                npcs_present=result["npcs_present"],
                            ):
                                merged.append(sn)
                    if merged:
                        new_partners = merged
                    else:
                        new_partners = retained_partners

        if result.get("npcs_present") and new_partners:
            pres_names = [game_engine._get_npc_name(n) for n in result["npcs_present"] if game_engine._get_npc_name(n)]
            new_partners = [p for p in new_partners if any(game_engine.is_dialogue_partner(p, [pn]) for pn in pres_names)]
        else:
            new_partners = []

        result["dialogue_partners"] = new_partners
        result["dialogue_partner"] = new_partners[0] if new_partners else None
        result["has_exited_convo"] = has_exited_convo

        if session.get("id") and new_node_id:
            try:
                from mechanics.world.locations.access_gate import record_turn_scene_residue
                gate_unlock_reason = stage_info.get("access_gate", {}).get("unlocked_by", "")
                record_turn_scene_residue(
                    session["id"], new_node_id, session, result, actions,
                    unlocked_by=gate_unlock_reason
                )
            except Exception:
                pass

    if isinstance(result, dict):
        result["_llm_system_prompt_list"] = final_system_prompt_list
        game_engine.sanitize_narrator_prose(
            result,
            session=session,
            party=party,
            actions=actions,
            present_npcs=result.get("npcs_present"),
        )
        outcome_narrative = (result.get("outcome_narrative") or outcome_narrative).strip()
        next_narrative = (result.get("next_narrative") or next_narrative).strip()

    if isinstance(result, dict):
        result["_llm_system_prompt_list"] = final_system_prompt_list
        result["_llm_user_prompt"] = user_prompt
        result, appended_encounter_text = ensure_enemy_encounter_narrative(
            result,
            session,
            party,
            actions=actions,
            pre_turn_enemy_names=pre_turn_enemy_names,
        )
        if appended_encounter_text:
            next_narrative = str(result.get("next_narrative") or "").strip()
            if stream_callback:
                try:
                    if getattr(stream_callback, "_accepts_field", False):
                        await stream_callback(f"\n\n{appended_encounter_text}", "next_narrative")
                    else:
                        await stream_callback(f"\n\n{appended_encounter_text}")
                except Exception:
                    pass

    res = result



    # --- ATTACH ADVANCED IN-GAME TIME & DAY/NIGHT PROGRESSION ---
    if not is_retry:
        if _pre_turn_sleep_info is not None:
            if isinstance(res, dict):
                res["_sleep_info"] = _pre_turn_sleep_info
                # Ensure outcome narrative reflects a refreshing sleep
                if not res.get("outcome_narrative") or "sleep" not in res.get("outcome_narrative", "").lower():
                    c_name = (party[0][0].get("name") if party and party[0] else "You") if isinstance(party[0], (tuple, list)) else "You"
                    wake_str = _pre_turn_sleep_info.get("clock_display", "07:00")
                    res["outcome_narrative"] = f"{c_name} turned in for the night, resting deeply until morning light broke across the horizon at {wake_str} AM. Vitals and energy are fully restored."
        elif _pre_turn_time_info is not None:
            if isinstance(res, dict):
                res["_time_info"] = _pre_turn_time_info
        elif session.get("id"):
            party_uids = [
                (char["user_id"] if isinstance(char, dict) else char[0]["user_id"])
                for char in party if char
            ]
            if actions and any(is_sleep_action(a.get("label", "")) for a in actions if isinstance(a, dict)):
                sleep_info = apply_sleep_rest(session["id"], party_uids, scen_key=scen_key)
                if isinstance(res, dict):
                    res["_sleep_info"] = sleep_info
                    # Ensure outcome narrative reflects a refreshing sleep
                    if not res.get("outcome_narrative") or "sleep" not in res.get("outcome_narrative", "").lower():
                        c_name = (party[0][0].get("name") if party and party[0] else "You") if isinstance(party[0], (tuple, list)) else "You"
                        wake_str = sleep_info.get("clock_display", "07:00")
                        res["outcome_narrative"] = f"{c_name} turned in for the night, resting deeply until morning light broke across the horizon at {wake_str} AM. Vitals and energy are fully restored."
            else:
                first_act = actions[0] if actions else {}
                is_dialogue_active = bool(new_partners)
                is_combat_active = bool(game_engine.get_active_enemies(session) or (isinstance(res, dict) and game_engine.get_active_enemies(res)))
                old_loc_val = session.get("current_location", "")
                new_loc_val = (res.get("location") if isinstance(res, dict) else None) or old_loc_val
                time_delta = calculate_action_time_cost(
                    first_act,
                    scen_key=scen_key,
                    old_loc=old_loc_val,
                    new_loc=new_loc_val,
                    is_dialogue=is_dialogue_active,
                    is_combat=is_combat_active,
                    session_id=session["id"]
                )
                time_report = advance_time(session["id"], time_delta, party_uids=party_uids)
                if isinstance(res, dict):
                    res["_time_info"] = time_report



    # Subsystem 3: Deterministic Invariant Verifier (Hallucination Guardrail)

    if isinstance(res, dict):

        dead_list = session.get("dead_characters", [])

        if res.get("deceased_characters"):

            dead_list.extend(res["deceased_characters"])

        

        # Cross-reference speaking characters against known dead

        if res.get("speaking_characters"):

            speakers = [s.strip().lower() for s in res["speaking_characters"]]

            for dead in dead_list:

                d_lower = dead.strip().lower()

                if d_lower in speakers:

                    log.warning(f"Invariant Violation caught: Deceased NPC '{dead}' spoke. Applying hallucination mask.")

                    if res.get("next_narrative"):
                        res["next_narrative"] += f"\n\n*(A cold wind blows. The words of {dead} echo in your mind, but they are gone. It is merely a memory...)*"

        # Register contact request cooldown before building next turn choices if attempt failed
        if session.get("id") and actions:
            for a in actions:
                if not isinstance(a, dict):
                    continue
                a_lbl = str(a.get("label") or a.get("text") or "").lower()
                a_intent = str(a.get("intent") or "").lower()
                is_contact = (
                    a_intent == "phone_contact_exchange"
                    or any(kw in a_lbl for kw in ("phone number", "contact info", "line id"))
                )
                if is_contact:
                    chk = a.get("check")
                    chk_tier = getattr(chk, "tier", None) or (chk.get("tier") if isinstance(chk, dict) else None)
                    if chk_tier in ("fail", "crit_fail"):
                        tgt = a.get("target_npc") or a.get("combat_target")
                        if not tgt:
                            tgt_partners = (
                                res.get("dialogue_partners")
                                or stage_info.get("new_partners")
                                or session.get("dialogue_partners")
                                or []
                            )
                            if tgt_partners:
                                tgt = tgt_partners[0]
                        if tgt:
                            try:
                                db.set_contact_request_cooldown(session["id"], str(tgt), hours=24, until_next_day=True)
                                log.info("[ContactCooldown] Registered failed contact exchange cooldown for '%s' in session %s until next day.", tgt, session["id"])
                            except Exception:
                                pass

        raw_turn_choices = result.get("next_choices") if result.get("next_choices") is not None else result.get("choices")
        hybrid_choices = game_engine.build_hybrid_turn_choices(
            raw_turn_choices or [],
            session=session,
            party=party,
            result=res,
            actions=actions,
            stage_info=stage_info,
            schedule_transition_choice=schedule_transition_choice,
            schedule_stay_choice=schedule_stay_choice,
        )
        res["choices"] = hybrid_choices
        res["next_choices"] = hybrid_choices
        res["_hybrid_choices_built"] = True

    if isinstance(res, dict):
        if "focal_point" in stage_info:
            res["focal_point"] = stage_info["focal_point"]
            session["focal_point"] = stage_info["focal_point"]
        if session.get("id"):
            try:
                db_updates = {}
                if "focal_point" in stage_info:
                    db_updates["focal_point"] = stage_info["focal_point"] or ""
                if res.get("location"):
                    db_updates["current_location"] = res["location"]
                if res.get("current_node_id"):
                    db_updates["current_node_id"] = res["current_node_id"]
                if "previous_node_id" in session:
                    db_updates["extra"] = {"previous_node_id": session["previous_node_id"]}
                if db_updates:
                    db.update_session(session["id"], **db_updates)
            except Exception:
                pass
        if stage_info.get("schedule_departed_npcs"):
            res["schedule_departed_npcs"] = stage_info["schedule_departed_npcs"]

        try:
            from game_engine.pronoun_resolver import annotate_turn_pronouns
            res = annotate_turn_pronouns(res, session=session, party=party)
        except Exception:
            pass

    return res


async def evaluate_action(
    session_id: int,
    user_action: str,
    party: list,
    current_location: str = "",
    current_npcs: list | None = None,
    nearby_enemies: list | None = None,
    history_text: str = "",
) -> dict:
    """Evaluate a synthetic or system-initiated action against a session via resolve_turn."""
    import db
    from skill_check import CheckResult
    session = db.get_session(session_id) or {
        "id": session_id,
        "current_location": current_location,
        "current_npcs": current_npcs or [],
        "nearby_enemies": nearby_enemies or [],
        "history": [history_text] if history_text else [],
    }
    session.setdefault("history", [history_text] if history_text else [])
    actor_char = (
        party[0][0]
        if party and isinstance(party[0], (list, tuple)) and party[0]
        else (party[0] if party and isinstance(party[0], dict) else {"name": "Adventurer", "user_id": 0, "max_hp": 100})
    )
    actions = [{
        "char": actor_char,
        "character": actor_char,
        "label": user_action,
        "action": user_action,
        "mp_spent": 0,
        "check": CheckResult(
            chance=100, roll=100.0, tier="success",
            tier_label="Success", succeeded=True, requirement=0
        ),
        "roll": None,
        "stat": "CHA",
        "stat_mod": 0,
        "total": None,
    }]
    outcome = await resolve_turn(session, party, actions)
    if hasattr(outcome, "to_dict"):
        d = outcome.to_dict()
    elif isinstance(outcome, dict):
        d = dict(outcome)
    else:
        d = {}
    d.setdefault("outcome_narrative", d.get("next_narrative") or d.get("narrative", ""))
    d.setdefault("npcs_present", d.get("current_npcs", current_npcs or []))
    d.setdefault("location", d.get("new_location") or current_location)
    return d






