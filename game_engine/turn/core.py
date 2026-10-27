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

    # Pre-turn deterministic causal pipeline (D3):
    # Spatial/Dijkstra runs FIRST inside compute_pre_turn_stage, then _stage_clock_after_movement
    # computes the exact clock advancement in memory WITHOUT mutating SQLite before the LLM finishes!
    _pre_turn_sleep_info = None
    _pre_turn_time_info = None
    _staged_time_op = None
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

        def _stage_clock_after_movement(
            is_movement: bool = False,
            effective_location: str = "",
            travel_minutes: int | None = None,
            blocked_invalid_exit: bool = False,
        ) -> None:
            nonlocal _pre_turn_sleep_info, _pre_turn_time_info, _staged_time_op
            from mechanics.system.time_engine import (
                get_location_sleep_context,
                is_nap_action,
                format_clock,
                get_day_of_week,
            )
            from mechanics.world.world_schedule import get_scenario_wake_minute

            first_act = actions[0] if actions else {}
            first_lbl = str(first_act.get("label") or "") if isinstance(first_act, dict) else str(first_act)
            explicit_skip = max(
                [int((a.get("skip_minutes") or 0) if isinstance(a, dict) else 0) for a in (actions or [])] or [0]
            )
            sleep_mode = ""
            for a_sm in (actions or []):
                if isinstance(a_sm, dict) and a_sm.get("sleep_mode"):
                    sleep_mode = str(a_sm["sleep_mode"]).lower()
                    break

            curr_loc_str = effective_location or session.get("current_location", "")
            sleep_ctx = get_location_sleep_context(
                curr_loc_str,
                props=session.get("physical_state", {}).get("props") if isinstance(session.get("physical_state"), dict) else None,
                scenario=scen_key,
                session_id=session_id_val,
            )

            is_sleep = any(is_sleep_action(a.get("label", "") if isinstance(a, dict) else str(a)) for a in (actions or [])) or sleep_mode == "sleep"
            is_nap, nap_dur = is_nap_action(first_lbl)
            if sleep_mode == "nap" and explicit_skip > 0:
                is_nap, nap_dur = True, explicit_skip

            if not session_id_val:
                if is_sleep:
                    session["current_day"] = prev_day + 1
                    session["current_minute"] = 420
                else:
                    time_delta = 0 if blocked_invalid_exit else (
                        max(0, int(travel_minutes))
                        if (is_movement and travel_minutes is not None)
                        else calculate_action_time_cost(
                            first_act,
                            scen_key=scen_key,
                            old_loc=session.get("current_location", ""),
                            new_loc=curr_loc_str,
                            is_dialogue=False,
                            is_combat=False,
                            session_id=0,
                        )
                    )
                    session["current_day"] = prev_day + ((prev_min + time_delta) // 1440)
                    session["current_minute"] = (prev_min + time_delta) % 1440
                return

            if is_sleep:
                wake_m = int(get_scenario_wake_minute(scen_key))
                if sleep_ctx.get("can_sleep", False):
                    rec_ratio = float(sleep_ctx.get("recovery_ratio", 1.0))
                    new_day = prev_day + 1 if prev_min >= wake_m else prev_day
                    new_min = wake_m
                    surf_lbl = sleep_ctx.get("surface_label", "Bed")
                    _staged_time_op = {
                        "op": "sleep",
                        "scen_key": scen_key,
                        "recovery_ratio": rec_ratio,
                        "surface_label": surf_lbl,
                        "party_uids": party_uids,
                    }
                    _pre_turn_sleep_info = {
                        "session_id": session_id_val,
                        "new_day": new_day,
                        "new_minute": new_min,
                        "clock_display": format_clock(new_min),
                        "day_name": get_day_of_week(new_day),
                        "fatigue_cleared": [],
                        "hp_restored": True,
                        "mp_restored": True,
                        "recovery_ratio": rec_ratio,
                        "surface_label": surf_lbl,
                    }
                    session["current_day"] = new_day
                    session["current_minute"] = new_min
                else:
                    wait_minutes = (wake_m - prev_min) if wake_m > prev_min else (1440 - prev_min + wake_m)
                    new_day = prev_day + ((prev_min + wait_minutes) // 1440)
                    new_min = (prev_min + wait_minutes) % 1440
                    _staged_time_op = {"op": "advance", "delta_minutes": wait_minutes, "party_uids": party_uids}
                    _pre_turn_time_info = {
                        "session_id": session_id_val,
                        "old_day": prev_day,
                        "new_day": new_day,
                        "old_minute": prev_min,
                        "new_minute": new_min,
                        "days_elapsed": new_day - prev_day,
                        "minutes_elapsed": wait_minutes,
                        "day_rolled_over": new_day > prev_day,
                        "fatigue_applied": [],
                    }
                    session["current_day"] = new_day
                    session["current_minute"] = new_min
            elif is_nap:
                new_day = prev_day + ((prev_min + nap_dur) // 1440)
                new_min = (prev_min + nap_dur) % 1440
                if sleep_ctx.get("can_sleep", False):
                    rec_ratio = float(sleep_ctx.get("recovery_ratio", 1.0))
                    surf_lbl = sleep_ctx.get("surface_label", "Bed")
                    _staged_time_op = {
                        "op": "nap",
                        "nap_minutes": nap_dur,
                        "recovery_ratio": rec_ratio,
                        "surface_label": surf_lbl,
                        "party_uids": party_uids,
                    }
                    _pre_turn_sleep_info = {
                        "session_id": session_id_val,
                        "new_day": new_day,
                        "new_minute": new_min,
                        "clock_display": format_clock(new_min),
                        "day_name": get_day_of_week(new_day),
                        "nap_minutes": nap_dur,
                        "recovery_ratio": rec_ratio,
                        "surface_label": surf_lbl,
                    }
                else:
                    _staged_time_op = {"op": "advance", "delta_minutes": nap_dur, "party_uids": party_uids}
                    _pre_turn_time_info = {
                        "session_id": session_id_val,
                        "old_day": prev_day,
                        "new_day": new_day,
                        "old_minute": prev_min,
                        "new_minute": new_min,
                        "days_elapsed": new_day - prev_day,
                        "minutes_elapsed": nap_dur,
                        "day_rolled_over": new_day > prev_day,
                        "fatigue_applied": [],
                    }
                session["current_day"] = new_day
                session["current_minute"] = new_min
            elif explicit_skip > 0 or sleep_mode == "wait":
                skip_m = explicit_skip if explicit_skip > 0 else 60
                new_day = prev_day + ((prev_min + skip_m) // 1440)
                new_min = (prev_min + skip_m) % 1440
                _staged_time_op = {"op": "advance", "delta_minutes": skip_m, "party_uids": party_uids}
                _pre_turn_time_info = {
                    "session_id": session_id_val,
                    "old_day": prev_day,
                    "new_day": new_day,
                    "old_minute": prev_min,
                    "new_minute": new_min,
                    "days_elapsed": new_day - prev_day,
                    "minutes_elapsed": skip_m,
                    "day_rolled_over": new_day > prev_day,
                    "fatigue_applied": [],
                }
                session["current_day"] = new_day
                session["current_minute"] = new_min
            else:
                from mechanics.world.mobility import get_session_dialogue_partners
                from mechanics.combat import is_in_combat
                is_dialogue_active = bool(get_session_dialogue_partners(session))
                is_combat_active = bool(is_in_combat(session))
                old_loc_val = session.get("current_location", "")
                if blocked_invalid_exit:
                    time_delta = 0
                elif is_movement and travel_minutes is not None:
                    time_delta = max(0, int(travel_minutes))
                else:
                    time_delta = calculate_action_time_cost(
                        first_act,
                        scen_key=scen_key,
                        old_loc=old_loc_val,
                        new_loc=curr_loc_str,
                        is_dialogue=is_dialogue_active,
                        is_combat=is_combat_active,
                        session_id=session_id_val,
                    )
                new_day = prev_day + ((prev_min + time_delta) // 1440)
                new_min = (prev_min + time_delta) % 1440
                _staged_time_op = {"op": "advance", "delta_minutes": time_delta, "party_uids": party_uids}
                _pre_turn_time_info = {
                    "session_id": session_id_val,
                    "old_day": prev_day,
                    "new_day": new_day,
                    "old_minute": prev_min,
                    "new_minute": new_min,
                    "days_elapsed": new_day - prev_day,
                    "minutes_elapsed": time_delta,
                    "day_rolled_over": new_day > prev_day,
                    "fatigue_applied": [],
                }
                session["current_day"] = new_day
                session["current_minute"] = new_min

            if _staged_time_op is not None:
                session["_staged_time_op"] = _staged_time_op
    else:
        _stage_clock_after_movement = None

    from game_engine.npcs import compute_pre_turn_stage
    stage_info = compute_pre_turn_stage(
        session,
        actions,
        party=party,
        ctx=ctx,
        persist_db=False,
        stage_clock_cb=_stage_clock_after_movement,
    )
    new_partners = stage_info["new_partners"]
    has_exited_convo = stage_info["has_exited_convo"]
    effective_location = stage_info["effective_location"]
    pre_turn_stage_npcs = stage_info["stage_npcs"]
    movement_dest_str = stage_info["movement_dest_str"]

    from mechanics.combat import is_in_combat
    from game_engine.npcs.cast_planner import plan_pre_turn, render_stage_plan, apply_cast_events
    cast_plan = plan_pre_turn(
        session,
        party,
        actions,
        stage_info=stage_info,
        is_combat=bool(is_in_combat(session)),
        new_loc=effective_location,
        persist_db=False,
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
    _cand_core_partners = list(new_partners or [])
    for _existing_dp in get_session_dialogue_partners(session):
        if _existing_dp and _existing_dp not in _cand_core_partners:
            _cand_core_partners.append(_existing_dp)
    if not _cand_core_partners:
        _cand_core_partners = ["Partner"]

    _EROTIC_SUB_INTENTS_CORE = {
        "intercourse", "oral_give", "oral_receive", "oral_mutual",
        "manual_give", "manual_receive", "manual_mutual",
        "anal_give", "anal_receive", "anal_mutual",
    }
    _initiating_erotic_act = False
    _has_redress_or_aftercare_act = False
    for _pa in (actions or []):
        if not isinstance(_pa, dict):
            continue
        _pchk = _pa.get("check")
        _ptier = getattr(_pchk, "tier", None) or (_pchk.get("tier") if isinstance(_pchk, dict) else None)
        _pa_ok = not (_pa.get("success") is False or _ptier in ("fail", "crit_fail"))
        _pa_ri = _pa.get("resolved_intent") if isinstance(_pa.get("resolved_intent"), dict) else {}
        _pa_sub = str(_pa_ri.get("sub_intent") or _pa.get("sub_intent") or "").lower().strip()
        _pa_int = str(_pa_ri.get("intent") or _pa.get("intent") or "").lower().strip()
        if _pa_sub in ("aftercare", "redress"):
            _has_redress_or_aftercare_act = True
        if not _pa_ok:
            continue
        if _pa_sub in _EROTIC_SUB_INTENTS_CORE or (_pa_int == "intimate_act" and _pa_sub not in ("kiss", "foreplay", "aftercare", "redress", "")):
            _initiating_erotic_act = True
            break
        if not _pa_sub and not _pa_int:
            _pa_lbl = str(_pa.get("label") or "")
            if _pa_lbl:
                for _cp_cand in _cand_core_partners:
                    if _core_classify_act(_pa_lbl, intimate_contact_str=_pre_ic_str, partner_name=_cp_cand).get("act_type", "none") not in ("none", "foreplay_nongenital"):
                        _initiating_erotic_act = True
                        break
            if _initiating_erotic_act:
                break

    _in_intimate_for_core = (
        not _core_is_disengage(actions)
        and (_core_is_erotic(_pre_ic_str) or _initiating_erotic_act)
    )
    _should_run_pre_intimacy = bool(
        _in_intimate_for_core
        or _core_is_erotic(_pre_ic_str)
        or _has_redress_or_aftercare_act
    )
    _in_aftercare_for_core = (not _core_is_disengage(actions)) and ("aftercare" in _pre_ic_str.lower() or _has_redress_or_aftercare_act)

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
    _pre_turn_incursion_notice = ""
    _pre_turn_incursion_directive = ""
    _skip_precompute_for_incursion = False
    if scenario_data.is_anomalous_incursions_scenario(session.get("scenario", "")) and actions and session.get("id"):
        first_inc_act = actions[0] if isinstance(actions[0], dict) else {}
        inc_lbl_low = str(first_inc_act.get("label") or "").strip().lower()
        inc_action_key = str(first_inc_act.get("incursion_action") or "").strip().lower()
        is_inc_tagged = bool(
            first_inc_act.get("incursion_id")
            or first_inc_act.get("intent") == "anomalous_incursion_action"
            or "(optional)" in inc_lbl_low
        )
        has_subdue_enemy_now = any(
            isinstance(e, dict) and e.get("requires_non_lethal_subdue") and e.get("hp", 0) > 0
            for e in (session.get("nearby_enemies") or [])
        )
        if not inc_action_key:
            if inc_lbl_low.startswith("🛡️ subdue & contain") or "subdue & contain" in inc_lbl_low:
                inc_action_key = "subdue"
            elif inc_lbl_low.startswith("🗣️ persuade / calm") or (
                has_subdue_enemy_now and ("persuade / calm" in inc_lbl_low or "(de-escalate)" in inc_lbl_low)
            ):
                inc_action_key = "combat_persuade"
            elif is_inc_tagged and inc_lbl_low.startswith("🗣️ [persuade]"):
                inc_action_key = "persuade"
            elif is_inc_tagged and inc_lbl_low.startswith("🕊️ [calm]"):
                inc_action_key = "calm"
            elif is_inc_tagged and inc_lbl_low.startswith("🧠 [outwit]"):
                inc_action_key = "outwit"
            elif is_inc_tagged and inc_lbl_low.startswith("🏗️ [use environment]"):
                inc_action_key = "environment"
            elif inc_lbl_low.startswith("🕊️ pacify & contain"):
                inc_action_key = "pacify"
            elif inc_lbl_low.startswith("🔬 analyze & seal"):
                inc_action_key = "analyze"
            elif inc_lbl_low.startswith("✨ use sealing ability"):
                inc_action_key = "seal_ability"
            elif inc_lbl_low.startswith("⚔️ engage anomalous breach"):
                inc_action_key = "attack"
        if inc_action_key:
            try:
                from mechanics.world.anomalous_events import (
                    resolve_non_hostile_incursion_action,
                    resolve_anomalous_combat_containment,
                )
                party_uids_inc = [
                    p[0].get("user_id")
                    for p in (party or [])
                    if p and isinstance(p[0], dict) and p[0].get("user_id")
                ]
                lead_inc_uid = party_uids_inc[0] if party_uids_inc else session.get("host_user_id")
                if inc_action_key in ("subdue", "combat_persuade"):
                    inc_res = resolve_anomalous_combat_containment(
                        session_id=int(session["id"]),
                        user_id=lead_inc_uid,
                        action_type=inc_action_key,
                        incursion_id=str(first_inc_act.get("incursion_id") or ""),
                        quest_id=str(first_inc_act.get("quest_id") or ""),
                        pre_rolled_check=first_inc_act.get("check"),
                        party_user_ids=party_uids_inc,
                    )
                else:
                    inc_res = resolve_non_hostile_incursion_action(
                        session_id=int(session["id"]),
                        incursion_id=str(first_inc_act.get("incursion_id") or ""),
                        user_id=lead_inc_uid,
                        action_type=inc_action_key,
                        stat_used=str(first_inc_act.get("stat") or ""),
                        pre_rolled_check=first_inc_act.get("check"),
                    )
                fresh_inc_sess = db.get_session(int(session["id"])) or {}
                session["nearby_enemies"] = fresh_inc_sess.get("nearby_enemies", [])
                session["daily_incursions"] = fresh_inc_sess.get("daily_incursions", session.get("daily_incursions", []))
                if inc_res.get("message"):
                    _pre_turn_incursion_notice = str(inc_res["message"])
                    _pre_turn_incursion_directive = (
                        f"[ANOMALOUS CONTAINMENT OUTCOME DIRECTIVE]:\n"
                        f"- {inc_res['message']}\n"
                        f"- Narrate this containment/engagement outcome vividly in `outcome_narrative` and `next_narrative`."
                    )
                if inc_res.get("combat_started") or inc_res.get("subdued") or inc_res.get("resolved"):
                    _skip_precompute_for_incursion = True
                elif inc_res.get("combat_continues") and isinstance(first_inc_act, dict):
                    # Failed in-combat Persuade/Calm or premature Subdue: enemy counter-attacks WITHOUT player dealing lethal weapon damage!
                    first_inc_act["combat_tactical_archetype"] = "combat_parley"
                    first_inc_act["tier"] = "fail"
                    first_inc_act["success"] = False
            except Exception as _inc_err:
                log.warning("Failed pre-turn anomalous incursion resolution: %s", _inc_err)

    mode = "combat" if (is_in_combat(session) and not _skip_precompute_for_incursion) else "narrative"
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
    if _pre_turn_incursion_directive:
        directive_note += f"\n{_pre_turn_incursion_directive}\n"

    # Pre-turn stage directives (hybrid sublocations, schedule shifts, canonical role spawns, tension timers)
    if stage_info.get("stage_directives"):
        for sdir in stage_info["stage_directives"]:
            if sdir and sdir not in directive_note:
                directive_note += f"\n{sdir}\n"

    if cast_plan is not None:
        stage_plan_text = render_stage_plan(cast_plan)
        directive_note += f"\n{stage_plan_text}\n"

    # --- DETERMINISTIC PRE-TURN ENGINES (Python-First, 0 Arbiter LLM calls) ---
    from game_engine.state.core import resolve_pre_turn_vitals_and_resources
    pre_vitals_res = resolve_pre_turn_vitals_and_resources(
        session, party, actions, persist_db=False
    )
    for p_dir in (pre_vitals_res.get("stage_directives") or pre_vitals_res.get("directives") or []):
        if p_dir and p_dir not in directive_note:
            directive_note += f"\n{p_dir}\n"

    from game_engine.state.social import resolve_pre_turn_social_and_disclosures
    pre_social_res = resolve_pre_turn_social_and_disclosures(
        session, party, actions, new_dialogue_partners=new_partners, persist_db=False
    )
    for s_dir in (pre_social_res.get("directives") or []):
        if s_dir and s_dir not in directive_note:
            directive_note += f"\n{s_dir}\n"

    hs_turn_events: dict = {}
    try:
        from mechanics.world.locations.seeds import is_school_scenario as _is_hs_scen
        if _is_hs_scen(session.get("scenario", "")):
            from mechanics.social.discreet_encounters import evaluate_high_school_turn_events
            hs_turn_events = evaluate_high_school_turn_events(
                session,
                party,
                actions,
                effective_location=str(effective_location or session.get("current_location") or ""),
                effective_node_id=str(stage_info.get("effective_node_id") or session.get("current_node_id") or ""),
            )
            if hs_turn_events.get("override_location"):
                effective_location = hs_turn_events["override_location"]
                session["current_location"] = effective_location
            if hs_turn_events.get("override_node_id"):
                stage_info["effective_node_id"] = hs_turn_events["override_node_id"]
                session["current_node_id"] = hs_turn_events["override_node_id"]
            if hs_turn_events.get("dialogue_partners"):
                session["dialogue_partners"] = list(hs_turn_events["dialogue_partners"])
                session["dialogue_partner"] = hs_turn_events["dialogue_partners"][0]
            for hs_dir in (hs_turn_events.get("directives") or []):
                if hs_dir and hs_dir not in directive_note:
                    directive_note += f"\n{hs_dir}\n"
    except Exception as _hs_ev_err:
        log.warning("Failed evaluating High School turn events: %s", _hs_ev_err)

    pre_intimate_res = None
    if _should_run_pre_intimacy:
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
    pre_quest_res = resolve_pre_turn_quests_and_clues(session, party, actions, persist_db=False)
    if _old_loc_for_quests:
        session["current_location"] = _old_loc_for_quests
    for q_dir in (pre_quest_res.get("directives") or []):
        if q_dir and q_dir not in directive_note:
            directive_note += f"\n{q_dir}\n"

    # in_dialogue_mode prevents duplicate stall directive injection — dialogue_prompt_block
    # is the single authoritative prompt section for dialogue stall notes.
    _pre_turn_dialogue_partners = [str(p).strip().lower() for p in (get_session_dialogue_partners(session) or []) if p]
    _in_dialogue_mode = bool(_pre_turn_dialogue_partners)

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
    _enc_loc = str(effective_location or session.get("current_location") or "")
    _enc_nid = str(stage_info.get("effective_node_id") or session.get("current_node_id") or "")
    _has_active_incursion_here = False
    if scenario_data.is_anomalous_incursions_scenario(scen_key) and session.get("id"):
        try:
            from mechanics.world.anomalous_events import (
                get_active_incursion_at_location,
                is_non_hostile_entity_containment_waypoint,
            )
            from mechanics.world.waypoints.core import get_active_local_quest_hooks
            _has_active_incursion_here = bool(get_active_incursion_at_location(int(session["id"]), _enc_loc, _enc_nid))
            if not _has_active_incursion_here:
                _local_q_hooks = get_active_local_quest_hooks(int(session["id"]), _enc_loc) or []
                _has_active_incursion_here = any(is_non_hostile_entity_containment_waypoint(w) for w in _local_q_hooks)
        except Exception:
            _has_active_incursion_here = False
    if (
        not is_in_combat(session)
        and not _has_active_incursion_here
        and not is_retry
        and not _in_intimate_for_core
        and not _in_aftercare_for_core
        and scenario_data.is_mechanic_enabled(scen_key, "tactical_combat")
        and not is_hub_location(_enc_loc)
    ):
        from mechanics.combat.enemies import generate_balanced_encounter, should_allow_random_encounter
        allow_enc, enc_prob = should_allow_random_encounter(
            scen_key=scen_key,
            location_name=_enc_loc,
            location_id=_enc_nid,
            current_minute=int(session.get("current_minute", 720) or 720),
            session_id=int(session.get("id") or 0),
        )
        if allow_enc and random.random() < enc_prob:
            party_dicts = [char for char, _ in party] if party else []
            cur_chapter = session.get("current_chapter", 1)
            new_monsters, xp_mult = generate_balanced_encounter(
                party_dicts, scen_key, _enc_loc or "area", cur_chapter,
                language=session.get("narration_language") or session.get("language", "en")
            )
            for _m in new_monsters:
                if isinstance(_m, dict):
                    _m["is_random_encounter"] = True
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
                        from mechanics.world.locations import get_clean_leaf_location
                        eff_leaf = get_clean_leaf_location(effective_location) if effective_location else ""
                        loc_prompt_target = target_station_sub or eff_leaf or "Main Area"
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
                directive_note += build_conversation_prompt_directive(session, new_partners, party=party)
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
        # Guarantee all list-expected fields on `result` (including LLM extra fields) are actual lists
        # before any `.setdefault(..., [])` or `.append(...)` runs.
        for _list_key in (
            "character_outcomes",
            "relationship_updates",
            "quest_updates",
            "faction_updates",
            "npcs_present",
            "nearby_enemies",
            "new_entities",
            "cast_events",
            "choices",
            "next_choices",
            "npc_departures",
            "dead_enemies",
            "dead_monsters",
            "deceased_characters",
            "speaking_characters",
        ):
            if _list_key in result and not isinstance(result[_list_key], list):
                _raw_v = result[_list_key]
                if isinstance(_raw_v, dict):
                    result[_list_key] = [_raw_v] if _raw_v else []
                elif isinstance(_raw_v, str) and _raw_v.strip():
                    result[_list_key] = [_raw_v.strip()]
                else:
                    result[_list_key] = []
        if isinstance(result.get("character_outcomes"), list):
            for _co_item in result["character_outcomes"]:
                if isinstance(_co_item, dict):
                    for _sub_lk in ("items_gained", "items_lost", "status_effects"):
                        if _sub_lk in _co_item and not isinstance(_co_item[_sub_lk], list):
                            _sv = _co_item[_sub_lk]
                            if isinstance(_sv, dict):
                                _co_item[_sub_lk] = [_sv] if _sv else []
                            elif isinstance(_sv, str) and _sv.strip():
                                _co_item[_sub_lk] = [_sv.strip()]
                            else:
                                _co_item[_sub_lk] = []

        result["_llm_system_prompt_list"] = final_system_prompt_list
        result = game_engine.sync_hostile_entities(result, session)

        if precomputed is not None:
            result = reconcile_combat_results(session, result, precomputed, party=party)
        if _pre_turn_incursion_notice:
            result["_combat_resolved_notice"] = (
                f"{_pre_turn_incursion_notice}\n{result['_combat_resolved_notice']}".strip()
                if result.get("_combat_resolved_notice")
                else _pre_turn_incursion_notice
            )
            result["nearby_enemies"] = session.get("nearby_enemies", [])




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
        dot_dead_dicts = []

        for monster in hostiles:

            if isinstance(monster, dict):

                if monster.get("status_effects"):

                    tick_status_timers(monster)

                if monster.get("hp", 1) > 0:

                    surviving_hostiles.append(monster)

                else:

                    dot_dead.append(monster.get("name", "Enemy"))
                    dot_dead_dicts.append(dict(monster))

                    if not monster.get("requires_non_lethal_subdue"):
                        tier = monster.get("tier_rank", 1)
                        mult = monster.get("xp_multiplier", 1.0)
                        xp, gold = {1: (40, 15), 2: (75, 25), 3: (150, 60), 4: (260, 120), 5: (450, 250)}.get(tier, (75, 25))
                        dot_xp_gain += int(xp * mult)
                        dot_gold_gain += int(gold * mult)

            else:

                surviving_hostiles.append(monster)

        session["nearby_enemies"] = surviving_hostiles

        if dot_dead and isinstance(result, dict):
            dot_confiscated = False
            dot_killed_non_hostile = [
                d for d in dot_dead_dicts if isinstance(d, dict) and d.get("requires_non_lethal_subdue")
            ]
            dot_nh_notices: list[str] = []
            if dot_killed_non_hostile and session.get("id"):
                try:
                    from mechanics.world.anomalous_events import handle_killed_non_hostile_entity
                    party_uids_dot = [
                        p[0].get("user_id")
                        for p in (party or [])
                        if p and isinstance(p[0], dict) and p[0].get("user_id")
                    ]
                    lead_dot_nh = party_uids_dot[0] if party_uids_dot else session.get("host_user_id")
                    for nh_dead in dot_killed_non_hostile:
                        nh_res = handle_killed_non_hostile_entity(
                            session_id=int(session["id"]),
                            dead_enemy=nh_dead,
                            user_id=lead_dot_nh,
                            party_user_ids=party_uids_dot,
                            session=session,
                        )
                        if nh_res.get("message"):
                            dot_nh_notices.append(nh_res["message"])
                except Exception:
                    pass

            if scenario_data.is_anomalous_incursions_scenario(scen_key):
                try:
                    from mechanics.narrative.bounty import should_confiscate_anomalous_combat_loot
                    lead_dot_uid = party[0][0].get("user_id") if (party and party[0] and isinstance(party[0][0], dict)) else session.get("host_user_id")
                    dot_confiscated = should_confiscate_anomalous_combat_loot(
                        int(session.get("id") or 0),
                        session=session,
                        user_id=lead_dot_uid,
                        defeated_enemies=dot_dead_dicts,
                    )
                except Exception:
                    dot_confiscated = False
            if dot_confiscated or len(dot_killed_non_hostile) == len(dot_dead_dicts):
                dot_gold_gain = 0
            elif dot_gold_gain > 0:
                result["_combat_gold"] = int(result.get("_combat_gold", 0) or 0) + dot_gold_gain

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
                if len(dot_killed_non_hostile) == len(dot_dead_dicts) and dot_nh_notices:
                    msg = "\n".join(dot_nh_notices)
                else:
                    msg = (
                        f"⚔️ Victory! {', '.join(dot_dead)} succumbed to their wounds!\n**Rewards:** +{dot_xp_gain} XP, +0 Gold *(Taxpayer Mandate: All anomalous salvage & spoils requisitioned by Public Agency HQ)*"
                        if dot_confiscated
                        else f"⚔️ Victory! {', '.join(dot_dead)} succumbed to their wounds!\n**Rewards:** +{dot_xp_gain} XP, +{dot_gold_gain} Gold"
                    )
                    if dot_nh_notices:
                        msg += "\n" + "\n".join(dot_nh_notices)
                try:
                    dot_inc_ids = {
                        str(d.get("incursion_id"))
                        for d in dot_dead_dicts
                        if isinstance(d, dict) and d.get("incursion_id") and not d.get("requires_non_lethal_subdue")
                    }
                    if dot_inc_ids and session.get("id"):
                        from mechanics.world.anomalous_events import mark_hostile_incursion_resolved_on_victory
                        lead_dot_uid = party[0][0].get("user_id") if (party and party[0] and isinstance(party[0][0], dict)) else session.get("host_user_id")
                        for d_inc_id in dot_inc_ids:
                            inc_done_res = mark_hostile_incursion_resolved_on_victory(int(session["id"]), d_inc_id, user_id=lead_dot_uid)
                            if inc_done_res and inc_done_res.get("message"):
                                msg += f"\n{inc_done_res['message']}"
                except Exception:
                    pass

                if result.get("_combat_resolved_notice"):

                    if ", ".join(dot_dead) not in result["_combat_resolved_notice"]:

                        result["_combat_resolved_notice"] += "\n" + msg

                else:

                    result["_combat_resolved_notice"] = msg

                # Inject a loot choice unless confiscated or non-hostile target destroyed
                c_list = result.get("next_choices") or result.get("choices") or []
                filtered_c = [c for c in c_list if not any(kw in (str(c.get("label", "")) if isinstance(c, dict) else str(c)).lower() for kw in ("attack", "strike with", "loot", "search the fallen"))]
                if not dot_confiscated and len(dot_killed_non_hostile) < len(dot_dead_dicts):
                    loot_choice = {
                        "label": "Search and loot the fallen enemies",
                        "stat": "FREE",
                        "requirement": 0,
                        "mp_cost": 0,
                    }
                    c_list = [loot_choice] + filtered_c[:3]
                else:
                    c_list = filtered_c[:3]

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
        # Merge deterministic pre-turn character outcomes (vitals, MP, gold, loot, consumables)
        if pre_vitals_res and pre_vitals_res.get("character_outcomes"):
            res_cos = result.setdefault("character_outcomes", [])
            for pv_co in pre_vitals_res["character_outcomes"]:
                pv_name = str(pv_co.get("name", "")).strip().lower()
                existing_co = next((co for co in res_cos if isinstance(co, dict) and str(co.get("name", "")).strip().lower() == pv_name), None)
                if existing_co:
                    if pv_co.get("hp_change", 0) != 0:
                        existing_co["hp_change"] = pv_co["hp_change"]
                    if pv_co.get("mp_change", 0) != 0:
                        existing_co["mp_change"] = pv_co["mp_change"]
                    if pv_co.get("gold_change", 0) != 0:
                        existing_co["gold_change"] = pv_co["gold_change"]
                    for itm in pv_co.get("items_gained", []):
                        if itm not in existing_co.setdefault("items_gained", []):
                            existing_co["items_gained"].append(itm)
                    for itm_l in pv_co.get("items_lost", []):
                        if itm_l not in existing_co.setdefault("items_lost", []):
                            existing_co["items_lost"].append(itm_l)
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

                            act_gold_spent = sum(
                                int(a.get("gold_spent") or 0)
                                for a in (actions or [])
                                if isinstance(a, dict)
                                and not a.get("_gold_spend_blocked_on_fail")
                                and (
                                    len(party) <= 1
                                    or (a.get("char") or {}).get("name", "").strip().lower() == c_name.lower()
                                    or a.get("user_id") == char.get("user_id")
                                )
                            )
                            raw_gold = outcome.get("gold_change", 0)
                            if raw_gold and int(raw_gold) < 0 and act_gold_spent == 0:
                                log.info("[VitalsGuard] Suppressed ungrounded non-combat Gold deduction (%s) for '%s' (no authorized gold_spent in action).", raw_gold, c_name)
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
            if result.get("_is_fallback_narrative") or not outcome_narrative:
                curr_loc = session.get("current_location", "the area")
                lead_npc = next((game_engine._get_npc_name(n) for n in (session.get("current_npcs") or []) if n), None)
                npc_mention = f" beside {lead_npc}" if lead_npc else ""
                next_narrative = f"The atmosphere settles around {curr_loc}{npc_mention} as the immediate action resolves. The surrounding area remains active with subtle movement and tension, awaiting the party's next move."
                result["is_fallback"] = True
                result["_is_fallback_narrative"] = True
            else:
                paras = [p.strip() for p in re.split(r"\n\s*\n", outcome_narrative) if p.strip()]
                if len(paras) >= 2:
                    outcome_narrative = "\n\n".join(paras[:-1])
                    next_narrative = paras[-1]
                else:
                    next_narrative = ""



        result["outcome_narrative"] = outcome_narrative

        result["next_narrative"] = next_narrative



    result = namegen.resolve_tokens_deep(result, scenario=scen_key)

    game_engine._sanitize_outcome_person_names(result, session["id"], scen_key)

    if isinstance(result, dict) and is_location_engine_enabled(scen_key):
        old_loc = session.get("current_location", "")
        curr_nid = session.get("current_node_id") or (db.resolve_node_id_from_location(session["id"], old_loc) if session.get("id") else None)
        has_graph = bool(curr_nid)
        if result.get("_anomalous_extracted"):
            new_loc = result.get("location") or old_loc
            new_node_id = result.get("current_node_id") or session.get("current_node_id")
            focal_point = None
            stage_info.pop("focal_point", None)
        else:
            if stage_info.get("is_movement"):
                new_loc = effective_location or old_loc
            elif has_graph:
                new_loc = old_loc
            else:
                new_loc = result.get("location") or old_loc
            new_node_id = stage_info.get("effective_node_id") or (db.resolve_node_id_from_location(session["id"], new_loc) if session.get("id") and new_loc else None) or session.get("current_node_id")
            focal_point = stage_info.get("focal_point") if stage_info.get("focal_point") is not None else result.get("focal_point")

        result["location"] = new_loc
        result["current_node_id"] = new_node_id
        if focal_point is not None:
            result["focal_point"] = focal_point
        if new_loc != old_loc:
            staged_seed = (
                [dict(n) if isinstance(n, dict) else {"name": str(n)} for n in (pre_turn_stage_npcs or [])]
                if effective_location == new_loc
                else []
            )
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

        # Rendezvous Convergence on Arrival (staged for atomic commit in apply_outcome)
        completed_appt_npc_ids = []
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
                        if appt.get("npc_id"):
                            completed_appt_npc_ids.append(appt["npc_id"])
                        a_name = appt.get("npc_name", "")
                        if a_name:
                            if not any(game_engine.is_dialogue_partner(a_name, [game_engine._get_npc_name(n)]) for n in result["npcs_present"]):
                                result["npcs_present"].append({"name": a_name, "role": "Rendezvous Partner", "status_effects": ["Present"]})
                            if a_name not in new_partners:
                                new_partners.append(a_name)
                            has_exited_convo = False
            except Exception:
                pass
        if completed_appt_npc_ids:
            result["_completed_appointment_npc_ids"] = completed_appt_npc_ids

        if cast_plan is not None:
            cast_plan.present_npcs = list(result.get("npcs_present") or [])
            # If the player explicitly traveled to meet / speak with a named NPC and that NPC is present on arrival,
            # deterministically engage them in dialogue (unless stealth is active or player exited conversation)
            if not has_exited_convo and not cast_plan.has_exited_convo and not cast_plan.stealth_active:
                from mechanics.world.mobility import is_rendezvous_target
                for _pn_obj in cast_plan.present_npcs:
                    _pn_nm = game_engine._get_npc_name(_pn_obj).strip()
                    if _pn_nm and _pn_nm not in new_partners:
                        if is_rendezvous_target(_pn_nm.lower(), actions=actions, session_id=None, new_loc=new_loc):
                            new_partners.append(_pn_nm)
            if new_partners:
                for np_nm in new_partners:
                    if np_nm and np_nm not in cast_plan.dialogue_partners:
                        cast_plan.dialogue_partners.append(np_nm)
            raw_cast_events = result.get("cast_events") or []
            final_plan, cast_rejections = apply_cast_events(
                cast_plan,
                raw_cast_events,
                session=session,
                party=party,
                stage_info=stage_info,
                persist_db=False,
            )
            new_partners = final_plan.dialogue_partners
            result["_cast_rejections"] = cast_rejections
            if has_exited_convo or cast_plan.has_exited_convo:
                new_partners = []
                for n in final_plan.present_npcs:
                    if isinstance(n, dict):
                        if n.get("stage_role") == "active_partner":
                            n["stage_role"] = "room_bystander"
                        if n.get("attention_ring") == "ring_1_partner":
                            n["attention_ring"] = "ring_3_bystander"
                        if isinstance(n.get("micro_blocking"), dict) and n["micro_blocking"].get("proximity") == "conversational_distance":
                            n["micro_blocking"]["proximity"] = "across_room"
            result["npcs_present"] = final_plan.present_npcs
            session["current_npcs"] = final_plan.present_npcs
        elif has_exited_convo and result.get("npcs_present"):
            new_partners = []
            for n in result["npcs_present"]:
                if isinstance(n, dict):
                    if n.get("stage_role") == "active_partner":
                        n["stage_role"] = "room_bystander"
                    if n.get("attention_ring") == "ring_1_partner":
                        n["attention_ring"] = "ring_3_bystander"
                    if isinstance(n.get("micro_blocking"), dict) and n["micro_blocking"].get("proximity") == "conversational_distance":
                        n["micro_blocking"]["proximity"] = "across_room"

        if result.get("npcs_present") and new_partners:
            pres_names = [game_engine._get_npc_name(n) for n in result["npcs_present"] if game_engine._get_npc_name(n)]
            new_partners = [p for p in new_partners if any(game_engine.is_dialogue_partner(p, [pn]) for pn in pres_names)]
        else:
            new_partners = []

        result["dialogue_partners"] = new_partners
        result["dialogue_partner"] = new_partners[0] if new_partners else None
        result["has_exited_convo"] = has_exited_convo

        if departing_for_schedule:
            try:
                from mechanics.social.conversation_choices import relocate_departed_schedule_npcs
                relocate_departed_schedule_npcs(session, result, departing_for_schedule, stage_info=stage_info)
                new_partners = list(result.get("dialogue_partners") or [])
                has_exited_convo = bool(has_exited_convo or (not new_partners))
                result["has_exited_convo"] = has_exited_convo
            except Exception as _reloc_err:
                log.warning("Failed relocating departed schedule NPCs: %s", _reloc_err)

        if session.get("cast_state"):
            result["_staged_cast_state"] = session["cast_state"]
        if stage_info.get("unlocked_edges") or stage_info.get("unlocked_nodes") or stage_info.get("consumed_key_items"):
            result["_staged_spatial_mutations"] = {
                "unlocked_edges": stage_info.get("unlocked_edges") or [],
                "unlocked_nodes": stage_info.get("unlocked_nodes") or [],
                "consumed_key_items": stage_info.get("consumed_key_items") or [],
            }
        if session.get("id") and new_node_id:
            result["_staged_scene_residue"] = {
                "node_id": new_node_id,
                "unlocked_by": stage_info.get("access_gate", {}).get("unlocked_by", ""),
            }

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
        if isinstance(res, dict) and _staged_time_op is not None:
            res["_staged_time_op"] = _staged_time_op
        if _pre_turn_sleep_info is not None:
            if isinstance(res, dict):
                res["_sleep_info"] = _pre_turn_sleep_info
                c_name = (party[0][0].get("name") if party and party[0] else "You") if isinstance(party[0], (tuple, list)) else "You"
                surf_lbl = _pre_turn_sleep_info.get("surface_label", "bed").lower()
                wake_str = _pre_turn_sleep_info.get("clock_display", "07:00")
                if "nap_minutes" in _pre_turn_sleep_info:
                    nap_m = _pre_turn_sleep_info["nap_minutes"]
                    res["outcome_narrative"] = f"{c_name} took a {nap_m}-minute rest on the {surf_lbl}. Energy is partially restored."
                else:
                    res["outcome_narrative"] = f"{c_name} turned in for the night on the {surf_lbl}, resting until {wake_str} AM. Vitals and energy are restored."
        elif _pre_turn_time_info is not None:
            if isinstance(res, dict):
                res["_time_info"] = _pre_turn_time_info
        elif _staged_time_op is None and session.get("id"):
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

        if not is_retry and new_partners and not _in_intimate_for_core and not game_engine.get_active_enemies(res):
            try:
                from mechanics.social.conversation_choices import record_partner_conversation_turn
                lead_p_rec = str(new_partners[0]).strip()
                was_partner_before = lead_p_rec.lower() in _pre_turn_dialogue_partners
                record_partner_conversation_turn(
                    session,
                    lead_p_rec,
                    actions,
                    party=party,
                    current_npcs=res.get("npcs_present") or session.get("current_npcs"),
                    was_already_partner=was_partner_before,
                    persist_db=True,
                )
            except Exception as _led_err:
                log.warning("Failed recording partner conversation turn ledger: %s", _led_err)

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
        # Anomalous Incursions Chapter 11 Post-Game Epilogue & Endless Mode Choice Handling
        if scenario_data.is_anomalous_incursions_scenario(scen_key):
            act_lbl_joined = " ".join(
                str(a.get("label") or a.get("action") or "").lower()
                for a in (actions or []) if isinstance(a, dict)
            )
            if "continue in endless containment mode" in act_lbl_joined:
                session["epilogue_ready"] = False
                session["endless_mode_unlocked"] = True
                if session.get("id"):
                    try:
                        db.update_session(session["id"], extra={"epilogue_ready": False, "endless_mode_unlocked": True})
                    except Exception:
                        pass
                endless_note = (
                    "\n\n♾️ **[ENDLESS CONTAINMENT MODE UNLOCKED]**: Though the World-Ending Cataclysm has been averted, "
                    "the metropolitan watch never truly ends. Daily Incursions, Faction Dispatches, Promotion Ranks, and "
                    "Special Agent bonds remain open across all 20 districts."
                )
                res["next_narrative"] = (str(res.get("next_narrative") or "") + endless_note).strip()
            elif "conclude campaign (archive chronicle)" in act_lbl_joined:
                session["epilogue_ready"] = False
                session["campaign_archived"] = True
                if session.get("id"):
                    try:
                        db.update_session(session["id"], status="completed", extra={"epilogue_ready": False, "campaign_archived": True})
                    except Exception:
                        pass
                archive_note = (
                    "\n\n🏁 **[CHRONICLE ARCHIVED — CAMPAIGN COMPLETE]**: Your operative dossier and victory over the World-Ending Anomaly "
                    "have been permanently sealed into the highest annals of the containment archives."
                )
                res["next_narrative"] = (str(res.get("next_narrative") or "") + archive_note).strip()
            elif session.get("epilogue_ready") or res.get("epilogue_ready"):
                epilogue_opts = [
                    {
                        "label": "🏁 Conclude Campaign (Archive Chronicle)",
                        "stat": "FREE",
                        "requirement": 0,
                        "mp_cost": 0,
                        "intent": "epilogue_conclude_campaign",
                    },
                    {
                        "label": "♾️ Continue in Endless Containment Mode",
                        "stat": "FREE",
                        "requirement": 0,
                        "mp_cost": 0,
                        "intent": "epilogue_endless_mode",
                    },
                ]
                existing_lbls = {str(c.get("label") or "") for c in hybrid_choices if isinstance(c, dict)}
                hybrid_choices = [o for o in epilogue_opts if o["label"] not in existing_lbls] + hybrid_choices[:3]

            # Daily Anomalous Incursions & Quest Non-Hostile Containment Choices
            try:
                from mechanics.world.anomalous_events import (
                    get_active_incursion_at_location,
                    is_non_hostile_entity_containment_waypoint,
                    extract_non_hostile_entity_name,
                    get_non_hostile_entity_temperament,
                    get_temperament_scene_hint,
                    build_non_hostile_narrative_choices,
                )
                cur_enemies_end = session.get("nearby_enemies") or []
                lead_char_end = (party[0][0] if isinstance(party[0], (tuple, list)) else party[0]) if (party and party[0]) else None
                if cur_enemies_end:
                    for e_sub in cur_enemies_end:
                        if isinstance(e_sub, dict) and e_sub.get("requires_non_lethal_subdue") and int(e_sub.get("hp", 0) or 0) > 0:
                            e_hp = int(e_sub.get("hp", 10) or 10)
                            e_max = max(1, int(e_sub.get("max_hp", 40) or 40))
                            sub_pct = float(e_sub.get("subdue_threshold_pct") or 0.35)
                            ent_disp = e_sub.get("name", "Entity")
                            persuade_dc = 6 if e_hp <= max(1, int(e_max * 0.50)) else 8
                            persuade_lbl = f"🗣️ Persuade / Calm {ent_disp} (De-escalate)"
                            combat_nh_opts = []
                            if e_hp <= max(1, int(e_max * sub_pct)):
                                sub_lbl = f"🛡️ Subdue & Contain {ent_disp}"
                                if not any(sub_lbl.lower() in str(c.get("label", "")).lower() for c in hybrid_choices if isinstance(c, dict)):
                                    combat_nh_opts.append({
                                        "label": sub_lbl,
                                        "stat": "FREE",
                                        "requirement": 0,
                                        "mp_cost": 0,
                                        "intent": "anomalous_incursion_action",
                                        "incursion_action": "subdue",
                                        "incursion_id": e_sub.get("incursion_id", ""),
                                        "quest_id": e_sub.get("linked_quest_id", ""),
                                    })
                            if not any(persuade_lbl.lower() in str(c.get("label", "")).lower() for c in hybrid_choices if isinstance(c, dict)):
                                combat_nh_opts.append({
                                    "label": persuade_lbl,
                                    "stat": "CHA",
                                    "requirement": persuade_dc,
                                    "mp_cost": 0,
                                    "intent": "anomalous_incursion_action",
                                    "incursion_action": "combat_persuade",
                                    "incursion_id": e_sub.get("incursion_id", ""),
                                    "quest_id": e_sub.get("linked_quest_id", ""),
                                })
                            if combat_nh_opts:
                                hybrid_choices = combat_nh_opts + hybrid_choices
                elif session.get("id"):
                    eff_loc_end = str(res.get("location") or session.get("current_location") or "")
                    eff_nid_end = str(res.get("current_node_id") or session.get("current_node_id") or "")
                    from mechanics.world.waypoints.core import get_active_local_quest_hooks
                    local_q_hooks = get_active_local_quest_hooks(int(session["id"]), eff_loc_end) or []
                    nh_q_wp = next(
                        (
                            w for w in local_q_hooks
                            if is_non_hostile_entity_containment_waypoint(
                                w,
                                all_wps=db.get_quest_waypoints(int(session["id"]), str(w.get("quest_id") or ""), w.get("sub_obj_id")) or [],
                            )
                        ),
                        None,
                    )
                    if nh_q_wp:
                        q_id_nh = str(nh_q_wp.get("quest_id") or "")
                        so_id_nh = nh_q_wp.get("sub_obj_id")
                        ent_nm_q = extract_non_hostile_entity_name(nh_q_wp)
                        temp_q = get_non_hostile_entity_temperament(seed_key=q_id_nh, quest_notes=str(nh_q_wp.get("quest_notes") or ""))
                        nh_q_choices = build_non_hostile_narrative_choices(
                            ent_nm_q,
                            mode="quest",
                            char=lead_char_end if isinstance(lead_char_end, dict) else None,
                            quest_id=q_id_nh,
                            sub_obj_id=so_id_nh,
                            stage_index=int(nh_q_wp.get("stage_index", 2) or 2),
                            is_story_quest=bool(nh_q_wp.get("is_story_quest")),
                            contract_type=str(nh_q_wp.get("completion_trigger") or "skill_check"),
                        )
                        existing_apps = {
                            str(c.get("approach") or "")
                            for c in hybrid_choices
                            if isinstance(c, dict) and c.get("quest_id") == q_id_nh
                        }
                        missing_q_opts = [o for o in nh_q_choices if o.get("approach") not in existing_apps]
                        if missing_q_opts:
                            non_nh = [
                                c for c in hybrid_choices
                                if not (isinstance(c, dict) and c.get("quest_id") == q_id_nh)
                            ]
                            present_nh = [
                                c for c in hybrid_choices
                                if isinstance(c, dict) and c.get("quest_id") == q_id_nh
                            ]
                            hybrid_choices = (present_nh + missing_q_opts)[:4] + non_nh[:2]
                        temp_hint_q = get_temperament_scene_hint(ent_nm_q, temp_q)
                        if ent_nm_q.lower() not in str(res.get("next_narrative") or "").lower():
                            res["next_narrative"] = (
                                str(res.get("next_narrative") or "")
                                + f"\n\n🕊️ **[NON-HOSTILE ENTITY ENCOUNTER]**: {temp_hint_q}"
                            ).strip()
                    else:
                        active_inc = get_active_incursion_at_location(
                            int(session["id"]),
                            location_str=eff_loc_end,
                            node_id=eff_nid_end,
                        )
                        if active_inc and not active_inc.get("resolved"):
                            inc_id = active_inc["incursion_id"]
                            ent_nm = active_inc["entity_name"]
                            pref_stat = str(active_inc.get("preferred_stat") or "INT").upper()
                            inc_opts = []
                            if active_inc.get("subtype") == "hostile_breach":
                                inc_opts.append({
                                    "label": f"⚔️ Engage Anomalous Breach: {ent_nm} (Optional)",
                                    "stat": "STR",
                                    "requirement": 6,
                                    "mp_cost": 0,
                                    "intent": "anomalous_incursion_action",
                                    "incursion_action": "attack",
                                    "incursion_id": inc_id,
                                })
                            elif active_inc.get("subtype") == "non_hostile_entity":
                                inc_opts.extend(
                                    build_non_hostile_narrative_choices(
                                        ent_nm,
                                        mode="incursion",
                                        char=lead_char_end if isinstance(lead_char_end, dict) else None,
                                        incursion_id=inc_id,
                                    )
                                )
                            else:
                                inc_opts.append({
                                    "label": f"🔬 Analyze & Seal {ent_nm} (Optional)",
                                    "stat": pref_stat,
                                    "requirement": 7,
                                    "mp_cost": 0,
                                    "intent": "anomalous_incursion_action",
                                    "incursion_action": "analyze",
                                    "incursion_id": inc_id,
                                })
                            # Offer Sacred/Sealing Ability option if operative knows any ability
                            lead_uid_ch = party[0][0].get("user_id") if (party and party[0] and isinstance(party[0][0], dict)) else session.get("host_user_id")
                            if lead_uid_ch and active_inc.get("subtype") != "hostile_breach":
                                learned_sp = db.get_learned_spells(lead_uid_ch) or []
                                if learned_sp:
                                    inc_opts.append({
                                        "label": f"✨ Use Sealing Ability on {ent_nm} (Optional)",
                                        "stat": "INT",
                                        "requirement": 5,
                                        "mp_cost": 8,
                                        "intent": "anomalous_incursion_action",
                                        "incursion_action": "seal_ability",
                                        "incursion_id": inc_id,
                                    })
                            existing_lbls_inc = {str(c.get("label") or "") for c in hybrid_choices if isinstance(c, dict)}
                            hybrid_choices = [o for o in inc_opts if o["label"] not in existing_lbls_inc] + hybrid_choices[:3]
                            if ent_nm.lower() not in str(res.get("next_narrative") or "").lower():
                                extra_temp_note = ""
                                if active_inc.get("subtype") == "non_hostile_entity":
                                    inc_temp = get_non_hostile_entity_temperament(
                                        seed_key=inc_id,
                                        explicit=str(active_inc.get("temperament") or ""),
                                    )
                                    extra_temp_note = " " + get_temperament_scene_hint(ent_nm, inc_temp)
                                inc_callout = (
                                    f"\n\n🌀 **[ACTIVE ANOMALOUS INCURSION — OPTIONAL]**: {active_inc.get('description', '')}{extra_temp_note} "
                                    f"*(Manifestation: **{ent_nm}** — you may choose to engage/contain it for bonus rewards or bypass it safely.)*"
                                )
                                res["next_narrative"] = (str(res.get("next_narrative") or "") + inc_callout).strip()
            except Exception as _inc_ch_err:
                log.warning("Failed anomalous incursion choice injection: %s", _inc_ch_err)

        if hs_turn_events:
            if hs_turn_events.get("override_location"):
                res["location"] = hs_turn_events["override_location"]
            if hs_turn_events.get("override_node_id"):
                res["current_node_id"] = hs_turn_events["override_node_id"]
            if hs_turn_events.get("choices"):
                existing_hs_lbls = {str(c.get("label") or "") for c in hybrid_choices if isinstance(c, dict)}
                hs_prep = [c for c in hs_turn_events["choices"] if c.get("label") not in existing_hs_lbls]
                hybrid_choices = hs_prep + hybrid_choices[: max(1, 5 - len(hs_prep))]
            if hs_turn_events.get("callout") and hs_turn_events["callout"].strip() not in str(res.get("next_narrative") or ""):
                res["next_narrative"] = (str(res.get("next_narrative") or "") + hs_turn_events["callout"]).strip()

        try:
            from mechanics.stealth import inject_covert_exploration_choices
            hybrid_choices = inject_covert_exploration_choices(hybrid_choices, session)
        except Exception as _st_ch_err:
            log.warning("Failed covert choice injection: %s", _st_ch_err)

        if new_partners and not _in_intimate_for_core and not game_engine.get_active_enemies(res):
            try:
                from mechanics.social.conversation_choices import pin_dialogue_exit_last
                hybrid_choices = pin_dialogue_exit_last(hybrid_choices, new_partners, max_total=8)
            except Exception as _pin_err:
                log.warning("Failed pinning dialogue exit choice: %s", _pin_err)

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






