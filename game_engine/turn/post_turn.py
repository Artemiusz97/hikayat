from __future__ import annotations

import db
import game_engine
import namegen
import scenario_data
from typing import Any, Optional
from contextlib import nullcontext
from db import adb
from mechanics.combat import is_in_combat
from mechanics.social.relationships import safe_get_contacts
from mechanics.system.time_engine import calculate_action_time_cost, is_sleep_action
from models.llm_schemas import TurnOutcome
from .encounter_narrative import ensure_enemy_encounter_narrative
from .generation import log
from .phase_state import PreTurnState, PromptAssemblyState


async def run_post_turn_phase(
    session: dict,
    party: list,
    actions: list,
    pre_state: PreTurnState,
    llm_state: PromptAssemblyState,
    *,
    stream_callback=None,
    is_retry: bool = False,
) -> TurnOutcome:
    _anom_domain_res = pre_state._anom_domain_res
    _in_intimate_for_core = pre_state._in_intimate_for_core
    _pre_turn_dialogue_partners = pre_state._pre_turn_dialogue_partners
    _pre_turn_incursion_notice = pre_state._pre_turn_incursion_notice
    _pre_turn_site_items_by_uid = pre_state._pre_turn_site_items_by_uid
    _pre_turn_sleep_info = pre_state._pre_turn_sleep_info
    _pre_turn_time_info = pre_state._pre_turn_time_info
    _staged_domain_vitals = pre_state._staged_domain_vitals
    from game_engine.npcs.cast_planner import apply_cast_events
    from mechanics.combat import reconcile_combat_results
    from mechanics.system.time_engine import advance_time, apply_sleep_rest
    from mechanics.world.locations import is_location_engine_enabled
    _staged_time_op = pre_state._staged_time_op
    cast_plan = pre_state.cast_plan
    ctx = pre_state.ctx
    effective_location = pre_state.effective_location
    has_exited_convo = pre_state.has_exited_convo
    hs_turn_events = pre_state.hs_turn_events
    pre_intimate_res = pre_state.pre_intimate_res
    pre_quest_res = pre_state.pre_quest_res
    pre_social_res = pre_state.pre_social_res
    pre_turn_enemy_names = pre_state.pre_turn_enemy_names
    pre_turn_stage_npcs = pre_state.pre_turn_stage_npcs
    pre_vitals_res = pre_state.pre_vitals_res
    precomputed = pre_state.precomputed
    scen_key = pre_state.scen_key
    session_id_val = pre_state.session_id_val
    stage_info = pre_state.stage_info
    _next_prompt_epoch = llm_state._next_prompt_epoch
    departing_for_schedule = llm_state.departing_for_schedule
    final_system_prompt_list = llm_state.final_system_prompt_list
    new_partners = llm_state.new_partners
    result = llm_state.result
    schedule_stay_choice = llm_state.schedule_stay_choice
    schedule_transition_choice = llm_state.schedule_transition_choice
    user_prompt = llm_state.user_prompt

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
                    _co_item.pop("xp_change", None)
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
            result = await adb(reconcile_combat_results, session, result, precomputed, party=party)
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

                    _is_non_lethal_dot = bool(
                        isinstance(session, dict)
                        and (session.get("non_lethal_combat") or session.get("non_lethal_mode"))
                    )
                    tick_status_timers(monster, non_lethal_mode=_is_non_lethal_dot)

                if monster.get("hp", 1) <= 0:
                    # DoT kills must honour the 2-Stage Vessel Tether exactly like direct damage:
                    # Stage 1 reforms at 25% HP; Stage 2 unsealed dispersal blocks Vault capture (60% rewards).
                    try:
                        from mechanics.world.folklore_mechanics import get_enemy_tether_state, try_resolve_zero_hp_tether
                        if get_enemy_tether_state(monster):
                            _dot_teth = try_resolve_zero_hp_tether(monster)
                            if _dot_teth.get("outcome") == "unsealed_dispersion":
                                monster["prevent_vault_capture"] = True
                    except Exception:
                        pass

                if monster.get("hp", 1) > 0:

                    surviving_hostiles.append(monster)

                else:

                    dot_dead.append(monster.get("name", "Enemy"))
                    dot_dead_dicts.append(dict(monster))

                    if not monster.get("requires_non_lethal_subdue"):
                        tier = monster.get("tier_rank", 1)
                        mult = monster.get("xp_multiplier", 1.0)
                        if monster.get("prevent_vault_capture"):
                            mult = float(mult or 1.0) * 0.60
                        xp, gold = {1: (40, 15), 2: (75, 25), 3: (150, 60), 4: (260, 120), 5: (450, 250)}.get(tier, (75, 25))
                        dot_xp_gain += int(xp * mult)
                        dot_gold_gain += int(gold * mult)

            else:

                surviving_hostiles.append(monster)

        session["nearby_enemies"] = surviving_hostiles

        if dot_dead and isinstance(result, dict):
            from mechanics.combat import prune_dead_combat_state
            prune_dead_combat_state(session, surviving_hostiles, llm_outcome=result)
            result["nearby_enemies"] = surviving_hostiles
            if not surviving_hostiles and isinstance(session, dict) and isinstance(session.get("party_npcs"), list):
                result["party_npcs"] = session["party_npcs"]
                if session.get("id"):
                    try:
                        await adb(db.set_session_party_npcs, int(session["id"]), session["party_npcs"])
                    except Exception:
                        pass
            dot_confiscated = False
            dot_killed_non_hostile = [
                d for d in dot_dead_dicts if isinstance(d, dict) and d.get("requires_non_lethal_subdue")
            ]
            dot_nh_notices: list[str] = []
            def _run_dot_pre_checks() -> tuple[list[str], bool]:
                local_notices: list[str] = []
                local_confiscated = False
                if dot_killed_non_hostile and session.get("id"):
                    try:
                        from mechanics.world.anomalous_events import handle_killed_non_hostile_entity
                        party_uids_dot = [
                            p[0].get("user_id")
                            for p in (party or [])
                            if p and isinstance(p[0], dict) and p[0].get("user_id")
                        ]
                        lead_dot_nh = party_uids_dot[0] if party_uids_dot else session.get("host_user_id")
                        with db.UnitOfWork():
                            for nh_dead in dot_killed_non_hostile:
                                nh_res = handle_killed_non_hostile_entity(
                                    session_id=int(session["id"]),
                                    dead_enemy=nh_dead,
                                    user_id=lead_dot_nh,
                                    party_user_ids=party_uids_dot,
                                    session=session,
                                )
                                if nh_res.get("message"):
                                    local_notices.append(nh_res["message"])
                    except Exception:
                        pass

                if scenario_data.is_anomalous_incursions_scenario(scen_key):
                    try:
                        from mechanics.narrative.bounty import should_confiscate_anomalous_combat_loot
                        lead_dot_uid = party[0][0].get("user_id") if (party and party[0] and isinstance(party[0][0], dict)) else session.get("host_user_id")
                        local_confiscated = should_confiscate_anomalous_combat_loot(
                            int(session.get("id") or 0),
                            session=session,
                            user_id=lead_dot_uid,
                            defeated_enemies=dot_dead_dicts,
                        )
                    except Exception:
                        local_confiscated = False
                return local_notices, local_confiscated

            dot_nh_notices, dot_confiscated = await adb(_run_dot_pre_checks)
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
                    if dot_xp_gain > 0 and co.get("name"):
                        _auth_xp_map = result.setdefault("_auth_combat_xp", {})
                        _ck_low = str(co["name"]).strip().lower()
                        _auth_xp_map[_ck_low] = int(_auth_xp_map.get(_ck_low, 0) or 0) + int(dot_xp_gain)

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

                def _run_dot_victory_db_updates() -> list[str]:
                    extra_msgs: list[str] = []
                    dot_inc_flags: dict = {}
                    for d in dot_dead_dicts:
                        if not isinstance(d, dict) or d.get("requires_non_lethal_subdue"):
                            continue
                        _d_inc = str(d.get("incursion_id") or d.get("breach_id") or "")
                        if _d_inc:
                            dot_inc_flags[_d_inc] = bool(dot_inc_flags.get(_d_inc) or d.get("prevent_vault_capture"))
                    dot_locus_bosses = [
                        d for d in dot_dead_dicts
                        if isinstance(d, dict) and d.get("is_site_locus_boss") and not d.get("requires_non_lethal_subdue")
                    ]
                    if not ((dot_inc_flags and session.get("id")) or (dot_locus_bosses and session.get("id")) or dot_dead_dicts):
                        return extra_msgs
                    with db.UnitOfWork() as dot_uow_conn:
                        try:
                            if dot_inc_flags and session.get("id"):
                                from mechanics.world.anomalous_events import mark_hostile_incursion_resolved_on_victory
                                lead_dot_uid = party[0][0].get("user_id") if (party and party[0] and isinstance(party[0][0], dict)) else session.get("host_user_id")
                                for d_inc_id, d_prevent in dot_inc_flags.items():
                                    inc_done_res = mark_hostile_incursion_resolved_on_victory(
                                        int(session["id"]), d_inc_id, user_id=lead_dot_uid, prevent_vault_capture=d_prevent
                                    )
                                    if inc_done_res and inc_done_res.get("message"):
                                        extra_msgs.append(inc_done_res["message"])
                            if dot_locus_bosses and session.get("id"):
                                from mechanics.world.anomalous_sites import complete_site_pacification
                                lead_dot_uid_sb = party[0][0].get("user_id") if (party and party[0] and isinstance(party[0][0], dict)) else session.get("host_user_id")
                                seen_dot_sites: set[str] = set()
                                for d_sb in dot_locus_bosses:
                                    sid_dot = str(d_sb.get("anomalous_site_id") or session.get("current_node_id") or "").strip()
                                    if not sid_dot or sid_dot in seen_dot_sites:
                                        continue
                                    seen_dot_sites.add(sid_dot)
                                    pac_dot = complete_site_pacification(
                                        int(session["id"]),
                                        sid_dot,
                                        user_id=int(lead_dot_uid_sb or 1),
                                        method="locus_boss_slain",
                                        scen_key=str(session.get("scenario") or "anomalous_incursions"),
                                        current_day=int(session.get("current_day", 1) or 1),
                                        turn_number=len(session.get("history") or []) + 1,
                                    )
                                    if isinstance(pac_dot, dict) and pac_dot.get("message"):
                                        extra_msgs.append(pac_dot["message"])
                        except Exception:
                            pass

                        if dot_dead_dicts:
                            from mechanics.social.epistemic_engine import neutralize_witnesses_from_combat_or_skill
                            _b17_dot_ko = [
                                d for d in dot_dead_dicts
                                if isinstance(d, dict) and d.get("requires_non_lethal_subdue")
                            ]
                            _b17_dot_killed = [
                                d for d in dot_dead_dicts
                                if not (isinstance(d, dict) and d.get("requires_non_lethal_subdue"))
                            ]
                            neutralize_witnesses_from_combat_or_skill(
                                int(session_id_val or session.get("id") or 0),
                                defeated_npcs=_b17_dot_ko,
                                killed_npcs=_b17_dot_killed,
                                present_witnesses=result.get("npcs") or session.get("npcs") or [],
                                turn=int(session.get("turn_count") or 0),
                                location_node_id=str(session.get("current_node_id") or session.get("location") or ""),
                                mode="combat",
                                conn=dot_uow_conn,
                            )
                    return extra_msgs

                for _extra_dot_m in await adb(_run_dot_victory_db_updates):
                    msg += f"\n{_extra_dot_m}"
                if result.get("_combat_resolved_notice"):

                    if ", ".join(dot_dead) not in result["_combat_resolved_notice"]:

                        result["_combat_resolved_notice"] += "\n" + msg

                else:

                    result["_combat_resolved_notice"] = msg

                try:
                    from mechanics.combat.reconcile import award_post_combat_auto_loot
                    award_post_combat_auto_loot(
                        session,
                        party,
                        dot_dead_dicts or dot_dead,
                        result,
                        confiscated=dot_confiscated,
                        killed_non_hostiles_count=len(dot_killed_non_hostile),
                    )
                except Exception:
                    pass

                # Filter out obsolete weapon attacks and post-combat loot prompts (auto-loot already awarded)
                c_list = result.get("next_choices") or result.get("choices") or []
                filtered_c = [
                    c for c in c_list
                    if not any(
                        kw in (str(c.get("label", "")) if isinstance(c, dict) else str(c)).lower()
                        for kw in ("attack", "strike with", "loot", "search the fallen", "search the bodies", "gather spoils")
                    )
                ]
                c_list = filtered_c[:4]

                result["next_choices"] = c_list

                result["choices"] = c_list

                # Despawn summons

                session["current_npcs"] = [npc for npc in session.get("current_npcs", []) if not npc.get("is_summon")]

                result["npcs_present"] = session["current_npcs"]



    import character_data

    from mechanics.social.relationships import safe_clamp_delta

    outcome_narrative = ""
    next_narrative = ""
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
            if pre_quest_res.get("quests_advanced_this_turn"):
                result["_quests_advanced_this_turn"] = list(pre_quest_res["quests_advanced_this_turn"])

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

                _is_anom_rel_skip = False
                if target_npc:
                    try:
                        from mechanics.world.anomalous_events import is_anomalous_scene_entity
                        _is_anom_rel_skip = bool(is_anomalous_scene_entity(target_npc, session=session))
                    except Exception:
                        pass
                if target_npc and not _is_anom_rel_skip:
                    rel_updates = result.setdefault("relationship_updates", [])
                    target_ru = next(
                        (ru for ru in rel_updates if isinstance(ru, dict) and str(ru.get("npc_name", "")).strip().lower() == target_npc.lower()),
                        None
                    )
                    check_tier = "fail"
                    failed_stat = ""
                    for a in (actions or []):
                        t = getattr(a.get("check"), "tier", None) or (a.get("check", {}).get("tier") if isinstance(a.get("check"), dict) else None)
                        if t in ("fail", "crit_fail"):
                            check_tier = t
                            failed_stat = str(a.get("stat") or "").strip().upper()
                            break
                    if check_tier == "crit_fail":
                        penalty = -2
                    elif failed_stat == "CHA":
                        penalty = 0
                    else:
                        penalty = -1

                    if target_ru is not None:
                        cur_ds = int(target_ru.get("delta_score", 0) or 0)
                        if penalty == 0:
                            if cur_ds > 0:
                                target_ru["delta_score"] = 0
                                log.info("[VitalsGuard] Clamped CHA failed check consequence for %s to 0", target_npc)
                        elif cur_ds >= 0:
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
            _home_aff_bonus = 0
            if session_id_val:
                try:
                    from mechanics.world.locations.residences import get_player_owned_or_starter_property_for_node
                    _eff_aff_nid = str(
                        (stage_info.get("effective_node_id") if isinstance(stage_info, dict) else None)
                        or session.get("current_node_id")
                        or ""
                    )
                    if _eff_aff_nid:
                        _owned_aff = await adb(
                            get_player_owned_or_starter_property_for_node,
                            int(session_id_val),
                            _eff_aff_nid,
                            session=session,
                        )
                        if _owned_aff and _owned_aff.get("catalog_entry"):
                            _home_aff_bonus = int(_owned_aff["catalog_entry"].get("hangout_affinity_bonus") or 0)
                except Exception:
                    _home_aff_bonus = 0
            for ru in result["relationship_updates"]:
                if isinstance(ru, dict) and "delta_score" in ru:
                    _raw_d = safe_clamp_delta(ru["delta_score"], -20, 20)
                    if _home_aff_bonus > 0 and _raw_d >= 0:
                        _raw_d = safe_clamp_delta(_raw_d + _home_aff_bonus, -20, 20)
                    ru["delta_score"] = _raw_d

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
                outcome_narrative, next_narrative = game_engine.split_outcome_and_next_paragraphs(
                    outcome_narrative, next_narrative
                )



        result["outcome_narrative"] = outcome_narrative

        result["next_narrative"] = next_narrative



    result = namegen.resolve_tokens_deep(result, scenario=scen_key)

    game_engine._sanitize_outcome_person_names(result, session["id"], scen_key)

    if isinstance(result, dict) and is_location_engine_enabled(scen_key):
        old_loc = session.get("current_location", "")
        if result.get("_anomalous_extracted"):
            new_loc = result.get("location") or old_loc
            new_node_id = result.get("current_node_id") or session.get("current_node_id")
            focal_point = None
            stage_info.pop("focal_point", None)
        else:
            def _resolve_post_llm_location() -> tuple[str, Any, Any, Optional[str]]:
                with db.ReadUnitOfWork() if session.get("id") else nullcontext():
                    curr_nid = session.get("current_node_id") or (
                        db.resolve_node_id_from_location(session["id"], old_loc) if session.get("id") else None
                    )
                    has_graph = bool(curr_nid)
                    eff_nid_ov: Optional[str] = None
                    if stage_info.get("is_movement"):
                        r_loc = effective_location or old_loc
                    elif has_graph:
                        r_loc = old_loc
                        cand_post_nid = result.get("destination_node_id") or (
                            db.resolve_node_id_from_location(session["id"], result.get("location"))
                            if session.get("id") and result.get("location") and result.get("location") != old_loc
                            else None
                        )
                        if cand_post_nid and cand_post_nid != curr_nid and session.get("id"):
                            try:
                                from mechanics.world.locations.pathfinding import find_spatial_path
                                from mechanics.world.locations.movement import is_movement_action
                                has_move_or_quest_trigger = any(
                                    (isinstance(a, dict) and (a.get("is_quest_action") or a.get("quest_id") or a.get("target_location") or a.get("target_node_id") or a.get("intent") in ("movement", "travel", "fast_travel", "move", "social_invite", "accompanied_travel")))
                                    or is_movement_action(a.get("label", "") if isinstance(a, dict) else str(a))
                                    for a in (actions or [])
                                )
                                if has_move_or_quest_trigger and find_spatial_path(session["id"], curr_nid, cand_post_nid):
                                    r_loc = db.format_node_tiered_location(session["id"], cand_post_nid) or result.get("location") or old_loc
                                    eff_nid_ov = cand_post_nid
                            except Exception:
                                pass
                    else:
                        r_loc = result.get("location") or old_loc
                    r_nid = (
                        eff_nid_ov
                        or stage_info.get("effective_node_id")
                        or (db.resolve_node_id_from_location(session["id"], r_loc) if session.get("id") and r_loc else None)
                        or session.get("current_node_id")
                    )
                    r_fp = stage_info.get("focal_point") if stage_info.get("focal_point") is not None else result.get("focal_point")
                    return r_loc, r_nid, r_fp, eff_nid_ov

            new_loc, new_node_id, focal_point, _eff_nid_ov = await adb(_resolve_post_llm_location)
            if _eff_nid_ov:
                stage_info["effective_node_id"] = _eff_nid_ov

        result["location"] = new_loc
        result["current_node_id"] = new_node_id
        if focal_point is not None:
            result["focal_point"] = focal_point
        if new_loc != old_loc:
            if effective_location == new_loc:
                staged_seed = [dict(n) if isinstance(n, dict) else {"name": str(n)} for n in (pre_turn_stage_npcs or [])]
            else:
                # Filter old room bystanders out when location changed post-stage
                try:
                    t_comps, _ = game_engine.classify_scene_npcs(session, actions, old_primary=old_loc, dest_primary=new_loc)
                    staged_seed = [dict(n) if isinstance(n, dict) else {"name": str(n)} for n in (t_comps or [])]
                except Exception:
                    staged_seed = []
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
                from mechanics.system.commitments_engine import (
                    _canon_key,
                    get_active_rendezvous_at_node,
                )
                eff_day = int(
                    result.get("_staged_day")
                    or session.get("_staged_day")
                    or (ctx.clock.staged_day if ctx is not None else None)
                    or session.get("current_day")
                    or 1
                )
                eff_min = (
                    session.get("_staged_minute")
                    if session.get("_staged_minute") is not None
                    else (
                        ctx.clock.staged_minute
                        if ctx is not None and ctx.clock.staged_minute is not None
                        else session.get("current_minute")
                    )
                )
                probes = []
                for p_probe in (new_node_id, new_loc):
                    if p_probe and str(p_probe) not in probes:
                        probes.append(str(p_probe))

                def _load_rendezvous_bundle() -> tuple[list[dict], dict[str, dict], dict[str, dict]]:
                    w_appts: list[dict] = []
                    seen_cids: set = set()
                    c_by_k: dict[str, dict] = {}
                    pa_by_k: dict[str, dict] = {}
                    with db.ReadUnitOfWork():
                        for loc_probe in probes:
                            for r in get_active_rendezvous_at_node(
                                session["id"],
                                loc_probe,
                                current_day=eff_day,
                                current_minute=eff_min,
                                enforce_window=True,
                            ):
                                cid = r.get("id") or r.get("commitment_key")
                                if cid not in seen_cids:
                                    seen_cids.add(cid)
                                    w_appts.append(r)

                        if w_appts:
                            contacts_now = safe_get_contacts(session["id"], ensure_scene=False)
                            for kc in contacts_now:
                                k_nm = str(kc.get("name") or "").strip()
                                k_id = str(kc.get("npc_id") or "").strip()
                                for kk in (k_id, k_nm, _canon_key(k_nm) if k_nm else ""):
                                    if kk:
                                        c_by_k[str(kk).strip().lower()] = kc

                            try:
                                for pa in (db.get_active_rendezvous_appointments(session["id"]) or []):
                                    for pak in (pa.get("npc_id"), pa.get("npc_name"), _canon_key(str(pa.get("npc_name") or ""))):
                                        if pak:
                                            pa_by_k[str(pak).strip().lower()] = pa
                            except Exception:
                                pass
                    return w_appts, c_by_k, pa_by_k

                window_appts, contact_by_key, phone_appts_by_key = await adb(_load_rendezvous_bundle)

                if window_appts:

                    departed_lows = {
                        str(d.get("name") if isinstance(d, dict) else (d or "")).strip().lower()
                        for d in (result.get("npc_departures") or [])
                        if (d.get("name") if isinstance(d, dict) else d)
                    }
                    for appt in window_appts:
                        cand_pairs = []
                        for part in (appt.get("participants") or []):
                            if not isinstance(part, dict):
                                continue
                            pk = str(part.get("npc_id") or part.get("person_key") or "").strip()
                            if pk.lower() == "player" or pk.lower().startswith("player:"):
                                continue
                            kc = contact_by_key.get(pk.lower()) or contact_by_key.get(_canon_key(pk))
                            a_name = str((kc.get("name") if kc else "") or part.get("name") or pk.replace("_", " ").title()).strip()
                            pa_row = phone_appts_by_key.get(a_name.lower()) or phone_appts_by_key.get(pk.lower())
                            a_npc_id = str((pa_row.get("npc_id") if pa_row else "") or (kc.get("npc_id") if kc else "") or pk or a_name).strip()
                            if a_name:
                                cand_pairs.append((a_npc_id, a_name))
                        if not cand_pairs:
                            tgt = str(appt.get("target_entity") or "").strip()
                            if tgt and tgt.lower() not in ("player", "group"):
                                kc = contact_by_key.get(tgt.lower()) or contact_by_key.get(_canon_key(tgt))
                                a_name = str((kc.get("name") if kc else "") or tgt.replace("_", " ").title()).strip()
                                pa_row = phone_appts_by_key.get(a_name.lower()) or phone_appts_by_key.get(tgt.lower())
                                a_npc_id = str((pa_row.get("npc_id") if pa_row else "") or (kc.get("npc_id") if kc else "") or tgt or a_name).strip()
                                cand_pairs.append((a_npc_id, a_name))

                        for a_npc_id, a_name in cand_pairs:
                            if a_name.lower() in departed_lows:
                                continue
                            already_present = any(
                                game_engine.is_dialogue_partner(a_name, [game_engine._get_npc_name(n)])
                                for n in result["npcs_present"]
                            )
                            if not already_present and (new_loc != old_loc):
                                result["npcs_present"].append({"name": a_name, "role": "Rendezvous Partner", "status_effects": ["Present"]})
                                already_present = True
                            if already_present:
                                if a_npc_id and a_npc_id not in completed_appt_npc_ids:
                                    completed_appt_npc_ids.append(a_npc_id)
                                if a_name not in new_partners:
                                    new_partners.append(a_name)
                                has_exited_convo = False
            except Exception:
                pass
        if completed_appt_npc_ids:
            result["_completed_appointment_npc_ids"] = completed_appt_npc_ids

        if session.get("id") and scenario_data.is_anomalous_incursions_scenario(scen_key):
            try:
                from mechanics.world.anomalous_events import sync_non_hostile_anomaly_scene_presence as _sync_nh_pre_cast
                _tmp_anom_sess = dict(session, current_npcs=list(result.get("npcs_present") or []))
                result["npcs_present"] = await adb(
                    _sync_nh_pre_cast,
                    int(session["id"]),
                    session=_tmp_anom_sess,
                    location_str=str(new_loc or ""),
                    node_id=str(new_node_id or ""),
                    persist_db=False,
                )
            except Exception:
                pass

        if cast_plan is not None:
            cast_plan.present_npcs = list(result.get("npcs_present") or [])
            # If the player explicitly traveled to meet / speak with a named NPC and that NPC is present on arrival,
            # deterministically engage them in dialogue (unless stealth is active or player exited conversation)
            if not has_exited_convo and not cast_plan.has_exited_convo and not cast_plan.stealth_active:
                from mechanics.world.mobility import is_action_targeting_present_npc_meetup
                for _pn_obj in cast_plan.present_npcs:
                    _pn_nm = game_engine._get_npc_name(_pn_obj).strip()
                    if _pn_nm and _pn_nm not in new_partners:
                        if is_action_targeting_present_npc_meetup(_pn_nm, actions=actions):
                            new_partners.append(_pn_nm)
            if new_partners:
                for np_nm in new_partners:
                    if np_nm and np_nm not in cast_plan.dialogue_partners:
                        cast_plan.dialogue_partners.append(np_nm)
            # Stage-plan cast contract: register on-screen people the narrator depicted without
            # an arrive event (one bounded utility repair call; never spawns from prose alone).
            if not is_in_combat(session):
                try:
                    from game_engine.npcs.cast_contract import repair_cast_contract_violations
                    await repair_cast_contract_violations(
                        result,
                        present_npcs=cast_plan.present_npcs,
                        party=party,
                        session=session,
                        scenario_label=str(session.get("scenario") or ""),
                    )
                except Exception as _cc_err:
                    log.warning("Cast contract check failed: %s", _cc_err)
            raw_cast_events = result.get("cast_events") or []
            final_plan, cast_rejections = apply_cast_events(
                cast_plan,
                raw_cast_events,
                session=session,
                party=party,
                stage_info=stage_info,
                persist_db=False,
                narrative_text=f"{result.get('outcome_narrative') or ''}\n\n{result.get('next_narrative') or ''}",
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
        _ctx_q_enc = session.get("_active_quest_encounter") or (ctx.combat.active_quest_encounter if ctx is not None else None)
        if _ctx_q_enc:
            result["_active_quest_encounter"] = _ctx_q_enc
        if session.get("nearby_enemies") and not result.get("nearby_enemies"):
            result["nearby_enemies"] = session["nearby_enemies"]
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
        if stage_info.get("pending_folklore_ops"):
            fk_ops_copy = dict(stage_info["pending_folklore_ops"])
            if is_retry:
                fk_ops_copy["is_retry"] = True
            result["_staged_folklore_ops"] = fk_ops_copy
        if stage_info.get("pending_roster_ops"):
            from game_engine.npcs.stage_manager import _merge_staged_roster_ops
            _merge_staged_roster_ops(
                result.setdefault("_staged_roster_ops", {}),
                stage_info["pending_roster_ops"],
            )

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
        if _next_prompt_epoch is not None and not result.get("_is_fallback_narrative"):
            session["prompt_epoch"] = _next_prompt_epoch
            result["_prompt_epoch"] = _next_prompt_epoch
        result = game_engine.reconcile_implied_hostile_encounter(
            result,
            session,
            actions=actions,
        )
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
    if isinstance(res, dict) and (stage_info.get("pending_folklore_ops") or {}).get("treaty_violation_village"):
        if stage_info.get("effective_location"):
            res["location"] = stage_info["effective_location"]
            session["current_location"] = stage_info["effective_location"]
        if stage_info.get("effective_node_id"):
            res["current_node_id"] = stage_info["effective_node_id"]
            session["current_node_id"] = stage_info["effective_node_id"]
        res["nearby_enemies"] = []
        session["nearby_enemies"] = []



    # --- ATTACH ADVANCED IN-GAME TIME & DAY/NIGHT PROGRESSION ---
    if isinstance(res, dict) and _staged_domain_vitals is not None:
        res["_staged_domain_vitals"] = _staged_domain_vitals
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
                sleep_info = await adb(apply_sleep_rest, session["id"], party_uids, scen_key=scen_key)
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
                time_delta = await adb(
                    calculate_action_time_cost,
                    first_act,
                    scen_key=scen_key,
                    old_loc=old_loc_val,
                    new_loc=new_loc_val,
                    is_dialogue=is_dialogue_active,
                    is_combat=is_combat_active,
                    session_id=session["id"],
                )
                time_delta += int(_anom_domain_res.get("time_slip_min") or 0)
                time_report = await adb(advance_time, session["id"], time_delta, party_uids=party_uids)
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
                                await adb(db.set_contact_request_cooldown, session["id"], str(tgt), hours=24, until_next_day=True)
                                log.info("[ContactCooldown] Registered failed contact exchange cooldown for '%s' in session %s until next day.", tgt, session["id"])
                            except Exception:
                                pass

        if not is_retry and new_partners and not _in_intimate_for_core and not game_engine.get_active_enemies(res):
            try:
                from mechanics.social.conversation_choices import record_partner_conversation_turn
                lead_p_rec = str(new_partners[0]).strip()
                was_partner_before = lead_p_rec.lower() in _pre_turn_dialogue_partners
                await adb(
                    record_partner_conversation_turn,
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
        hybrid_choices = await adb(
            game_engine.build_hybrid_turn_choices,
            raw_turn_choices or [],
            session=session,
            party=party,
            result=res,
            actions=actions,
            stage_info=stage_info,
            schedule_transition_choice=schedule_transition_choice,
            schedule_stay_choice=schedule_stay_choice,
        )
        # Universal Chapter 11 Post-Game Epilogue & Endless Mode Choice Handling (All Scenarios)
        _ep_intents = {
            str(a.get("intent") or "").strip().lower()
            for a in (actions or []) if isinstance(a, dict)
        }
        _is_epilogue_turn = bool(
            session.get("epilogue_ready")
            or res.get("epilogue_ready")
            or int(session.get("chapter") or 1) >= 11
            or ("epilogue_conclude_campaign" in _ep_intents)
            or ("epilogue_endless_mode" in _ep_intents)
        )
        if _is_epilogue_turn:
            from game_engine.quest_lifecycle import build_universal_epilogue_choices, resolve_epilogue_choice
            act_lbl_joined = " ".join(
                str(a.get("label") or a.get("action") or "").lower()
                for a in (actions or []) if isinstance(a, dict)
            )
            _chose_endless = (
                "epilogue_endless_mode" in _ep_intents
                or "continue in endless" in act_lbl_joined
                or "endless sandbox mode" in act_lbl_joined
            )
            _chose_archive = (
                "epilogue_conclude_campaign" in _ep_intents
                or "conclude campaign (archive chronicle)" in act_lbl_joined
                or "archive chronicle" in act_lbl_joined
            )
            if _chose_endless:
                session["epilogue_ready"] = False
                session["endless_mode_unlocked"] = True
                if session.get("id"):
                    try:
                        await adb(resolve_epilogue_choice, int(session["id"]), "epilogue_endless_mode", db.infer_session_turn(session))
                    except Exception:
                        pass
                endless_note = (
                    "\n\n♾️ **[ENDLESS SANDBOX MODE UNLOCKED]**: Though the overarching campaign climax has concluded, "
                    "your journey continues freely across the living world with side contracts, relationships, and regional events."
                )
                res["next_narrative"] = (str(res.get("next_narrative") or "") + endless_note).strip()
            elif _chose_archive:
                session["epilogue_ready"] = False
                session["campaign_archived"] = True
                session["chronicle_archived"] = True
                if session.get("id"):
                    try:
                        await adb(resolve_epilogue_choice, int(session["id"]), "epilogue_conclude_campaign", db.infer_session_turn(session))
                    except Exception:
                        pass
                archive_note = (
                    "\n\n🏁 **[CHRONICLE ARCHIVED — CAMPAIGN COMPLETE]**: Your party's deeds and legacy "
                    "have been permanently sealed into the annals of the chronicle."
                )
                res["next_narrative"] = (str(res.get("next_narrative") or "") + archive_note).strip()
            elif session.get("epilogue_ready") or res.get("epilogue_ready"):
                epilogue_opts = build_universal_epilogue_choices(scen_key)
                existing_lbls = {str(c.get("label") or "") for c in hybrid_choices if isinstance(c, dict)}
                hybrid_choices = [o for o in epilogue_opts if o["label"] not in existing_lbls] + hybrid_choices[:3]

        if scenario_data.is_anomalous_incursions_scenario(scen_key):
            # Daily Anomalous Incursions & Quest Non-Hostile Containment Choices
            dp_end = ""
            try:
                from mechanics.world.anomalous_events import (
                    get_active_incursion_at_location,
                    is_non_hostile_entity_containment_waypoint,
                    extract_non_hostile_entity_name,
                    get_non_hostile_entity_temperament,
                    get_temperament_scene_hint,
                    build_non_hostile_narrative_choices,
                    build_sapient_anomaly_dialogue_choices,
                    sync_non_hostile_anomaly_scene_presence,
                    is_anomalous_scene_entity,
                )
                if session.get("id"):
                    eff_loc_sync = str(res.get("location") or session.get("current_location") or "")
                    eff_nid_sync = str(res.get("current_node_id") or session.get("current_node_id") or "")
                    synced_npcs = await adb(
                        sync_non_hostile_anomaly_scene_presence,
                        int(session["id"]),
                        session=session,
                        location_str=eff_loc_sync,
                        node_id=eff_nid_sync,
                        persist_db=True,
                    )
                    res["npcs_present"] = synced_npcs
                cur_enemies_end = session.get("nearby_enemies") or []
                lead_char_end = (party[0][0] if isinstance(party[0], (tuple, list)) else party[0]) if (party and party[0]) else None
                if res.get("has_exited_convo"):
                    dp_end = ""
                elif "dialogue_partner" in res:
                    dp_end = str(res.get("dialogue_partner") or "").strip()
                else:
                    dp_end = str(session.get("dialogue_partner") or "").strip()
                if not cur_enemies_end and dp_end and is_anomalous_scene_entity(dp_end, session=session, current_npcs=res.get("npcs_present")):
                    hybrid_choices = build_sapient_anomaly_dialogue_choices(
                        dp_end,
                        session_id=int(session["id"]) if session.get("id") else None,
                        session=session,
                        char=lead_char_end if isinstance(lead_char_end, dict) else None,
                    )
                elif cur_enemies_end:
                    for e_sub in cur_enemies_end:
                        if isinstance(e_sub, dict) and (e_sub.get("requires_non_lethal_subdue") or e_sub.get("is_anomalous_manifestation")) and int(e_sub.get("hp", 0) or 0) > 0:
                            e_hp = int(e_sub.get("hp", 10) or 10)
                            e_max = max(1, int(e_sub.get("max_hp", 40) or 40))
                            e_sap = str(e_sub.get("sapience") or ("sapient" if e_sub.get("requires_non_lethal_subdue") else "instinctual")).strip().lower()
                            def_sub_pct = 0.50 if (not e_sub.get("requires_non_lethal_subdue") and e_sap == "instinctual") else 0.35
                            sub_pct = float(e_sub.get("subdue_threshold_pct") or def_sub_pct)
                            ent_disp = e_sub.get("name", "Entity")
                            is_tb_exp = bool(e_sub.get("taboo_exploited") or e_sub.get("taboo_seal_unlocked"))
                            is_dos_rev = bool(
                                e_sub.get("dossier_revealed")
                                or (isinstance(e_sub.get("anomaly_blueprint"), dict) and e_sub["anomaly_blueprint"].get("dossier_revealed"))
                            )
                            is_compulsive_ready = bool(e_sap == "compulsive" and (is_dos_rev or is_tb_exp))
                            persuade_dc = 6 if (e_hp <= max(1, int(e_max * 0.50)) or is_tb_exp) else 8
                            if is_dos_rev:
                                persuade_dc = max(4, persuade_dc - 2)
                            persuade_lbl = (
                                f"🗣️ Enact Counter-Rite / Calm {ent_disp}"
                                if e_sap == "compulsive"
                                else f"🗣️ Persuade / Calm {ent_disp} (De-escalate)"
                            )
                            combat_nh_opts = []
                            if e_hp <= max(1, int(e_max * sub_pct)) or bool(e_sub.get("is_breached")) or is_tb_exp:
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
                            if (e_sub.get("requires_non_lethal_subdue") or e_sap == "sapient" or is_compulsive_ready) and not any(persuade_lbl.lower() in str(c.get("label", "")).lower() for c in hybrid_choices if isinstance(c, dict)):
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
                    lead_uid_ch = party[0][0].get("user_id") if (party and party[0] and isinstance(party[0][0], dict)) else session.get("host_user_id")

                    def _load_incursion_choice_context() -> tuple[Any, list[dict], Any, list[dict], list[dict]]:
                        with db.ReadUnitOfWork():
                            local_q_hooks = get_active_local_quest_hooks(int(session["id"]), eff_loc_end) or []
                            nh_wp = next(
                                (
                                    w for w in local_q_hooks
                                    if is_non_hostile_entity_containment_waypoint(
                                        w,
                                        all_wps=db.get_quest_waypoints(int(session["id"]), str(w.get("quest_id") or ""), w.get("sub_obj_id")) or [],
                                    )
                                ),
                                None,
                            )
                            if nh_wp:
                                q_id_r = str(nh_wp.get("quest_id") or "")
                                so_id_r = nh_wp.get("sub_obj_id")
                                ent_r = extract_non_hostile_entity_name(nh_wp)
                                nh_c = build_non_hostile_narrative_choices(
                                    ent_r,
                                    mode="quest",
                                    char=lead_char_end if isinstance(lead_char_end, dict) else None,
                                    quest_id=q_id_r,
                                    sub_obj_id=so_id_r,
                                    stage_index=int(nh_wp.get("stage_index", 2) or 2),
                                    is_story_quest=bool(nh_wp.get("is_story_quest")),
                                    contract_type=str(nh_wp.get("completion_trigger") or "skill_check"),
                                    session_id=int(session["id"]),
                                    include_converse=True,
                                )
                                return nh_wp, nh_c, None, [], []
                            act_inc = get_active_incursion_at_location(
                                int(session["id"]),
                                location_str=eff_loc_end,
                                node_id=eff_nid_end,
                            )
                            inc_nh_c: list[dict] = []
                            lrn_sp: list[dict] = []
                            if act_inc and not act_inc.get("resolved"):
                                if act_inc.get("subtype") == "non_hostile_entity":
                                    inc_nh_c = build_non_hostile_narrative_choices(
                                        act_inc["entity_name"],
                                        mode="incursion",
                                        char=lead_char_end if isinstance(lead_char_end, dict) else None,
                                        incursion_id=act_inc["incursion_id"],
                                        breach_id=act_inc["incursion_id"],
                                        session_id=int(session["id"]),
                                        include_converse=True,
                                    )
                                if lead_uid_ch and act_inc.get("subtype") != "hostile_breach":
                                    lrn_sp = db.get_learned_spells(lead_uid_ch) or []
                            return None, [], act_inc, inc_nh_c, lrn_sp

                    nh_q_wp, nh_q_choices, active_inc, inc_nh_choices, learned_sp = await adb(_load_incursion_choice_context)
                    if nh_q_wp:
                        q_id_nh = str(nh_q_wp.get("quest_id") or "")
                        ent_nm_q = extract_non_hostile_entity_name(nh_q_wp)
                        temp_q = get_non_hostile_entity_temperament(seed_key=q_id_nh, quest_notes=str(nh_q_wp.get("quest_notes") or ""))
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
                            hybrid_choices = (present_nh + missing_q_opts)[:5] + non_nh[:2]
                        temp_hint_q = get_temperament_scene_hint(ent_nm_q, temp_q)
                        if ent_nm_q.lower() not in str(res.get("next_narrative") or "").lower():
                            res["next_narrative"] = (
                                str(res.get("next_narrative") or "")
                                + f"\n\n🕊️ **[NON-HOSTILE ENTITY ENCOUNTER]**: {temp_hint_q}"
                            ).strip()
                    else:
                        if active_inc and not active_inc.get("resolved"):
                            inc_id = active_inc["incursion_id"]
                            ent_nm = active_inc["entity_name"]
                            pref_stat = str(active_inc.get("preferred_stat") or "INT").upper()
                            inc_opts = []
                            if isinstance(active_inc.get("anomaly_blueprint"), dict) and not active_inc.get("dossier_revealed"):
                                inc_opts.append({
                                    "label": f"🔍 Scan Anomaly Dossier: {ent_nm} (Optional)",
                                    "stat": "PER",
                                    "requirement": 5,
                                    "mp_cost": 0,
                                    "intent": "anomalous_incursion_action",
                                    "incursion_action": "reveal_dossier",
                                    "incursion_id": inc_id,
                                    "breach_id": inc_id,
                                })
                            if active_inc.get("subtype") == "hostile_breach":
                                inc_opts.append({
                                    "label": f"⚔️ Engage Anomaly Breach: {ent_nm} (Optional)",
                                    "stat": "STR",
                                    "requirement": 6,
                                    "mp_cost": 0,
                                    "intent": "anomalous_incursion_action",
                                    "incursion_action": "attack",
                                    "incursion_id": inc_id,
                                    "breach_id": inc_id,
                                })
                            elif active_inc.get("subtype") == "non_hostile_entity":
                                inc_opts.extend(inc_nh_choices)
                            else:
                                inc_opts.append({
                                    "label": f"🔬 Analyze & Seal {ent_nm} (Optional)",
                                    "stat": pref_stat,
                                    "requirement": 7,
                                    "mp_cost": 0,
                                    "intent": "anomalous_incursion_action",
                                    "incursion_action": "analyze",
                                    "incursion_id": inc_id,
                                    "breach_id": inc_id,
                                })
                            # Offer Sacred/Sealing Ability option if operative knows any ability
                            if lead_uid_ch and active_inc.get("subtype") != "hostile_breach" and learned_sp:
                                inc_opts.append({
                                    "label": f"✨ Use Sealing Ability on {ent_nm} (Optional)",
                                    "stat": "INT",
                                    "requirement": 5,
                                    "mp_cost": 8,
                                    "intent": "anomalous_incursion_action",
                                    "incursion_action": "seal_ability",
                                    "incursion_id": inc_id,
                                    "breach_id": inc_id,
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
                                    f"\n\n🌀 **[ACTIVE ANOMALY BREACH — OPTIONAL]**: {active_inc.get('description', '')}{extra_temp_note} "
                                    f"*(Manifestation: **{ent_nm}** — you may choose to engage/contain it for bonus rewards or bypass it safely.)*"
                                )
                                res["next_narrative"] = (str(res.get("next_narrative") or "") + inc_callout).strip()
            except Exception as _inc_ch_err:
                log.warning("Failed anomalous incursion choice injection: %s", _inc_ch_err)

            try:
                if (
                    session.get("id")
                    and not game_engine.get_active_enemies(res)
                    and not game_engine.get_active_enemies(session)
                    and not dp_end
                ):
                    from mechanics.world.anomalous_sites import (
                        build_site_harvest_choices,
                        build_site_puzzle_choices,
                        has_quest_or_breach_priority_at_node,
                    )
                    _site_loc_end = str(res.get("location") or session.get("current_location") or "")
                    _site_nid_end = str(res.get("current_node_id") or session.get("current_node_id") or "")
                    _site_inv_end = (party[0][1] if (party and isinstance(party[0], (tuple, list)) and len(party[0]) > 1) else [])

                    def _build_site_post_choices_bundle() -> list[dict]:
                        with db.ReadUnitOfWork():
                            try:
                                _site_day_end, _site_min_end, _ = db.get_session_time(int(session["id"]))
                            except Exception:
                                _site_day_end = int(session.get("current_day", 1) or 1)
                                _site_min_end = int(session.get("current_minute", 720) or 720)
                            _has_site_prio = has_quest_or_breach_priority_at_node(
                                int(session["id"]),
                                location_str=_site_loc_end,
                                node_id=_site_nid_end,
                            )
                            if _has_site_prio:
                                return []
                            _puz_opts = build_site_puzzle_choices(
                                int(session["id"]),
                                location_str=_site_loc_end,
                                node_id=_site_nid_end,
                                scen_key=scen_key,
                                current_day=int(_site_day_end or 1),
                                current_minute=int(_site_min_end or 720),
                                inventory=_site_inv_end,
                                has_priority_event=False,
                                session=session,
                            )
                            _har_opts = build_site_harvest_choices(
                                int(session["id"]),
                                location_str=_site_loc_end,
                                node_id=_site_nid_end,
                                scen_key=scen_key,
                                current_day=int(_site_day_end or 1),
                                has_priority_event=False,
                            )
                            return _puz_opts + _har_opts

                    _site_opts = await adb(_build_site_post_choices_bundle)
                    if _site_opts:
                        _existing_site_lbls = {str(c.get("label") or "") for c in hybrid_choices if isinstance(c, dict)}
                        _new_site_opts = [o for o in _site_opts if o.get("label") not in _existing_site_lbls]
                        if _new_site_opts:
                            hybrid_choices = _new_site_opts + hybrid_choices[: max(1, 5 - len(_new_site_opts))]
            except Exception as _site_ch_err:
                log.warning("Failed anomalous site choice injection: %s", _site_ch_err)

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

        hybrid_choices = game_engine.order_choices_canonically(
            hybrid_choices,
            in_dialogue=bool(new_partners and not _in_intimate_for_core),
            in_combat=bool(game_engine.get_active_enemies(res) or game_engine.get_active_enemies(session)),
            in_intimate=bool(_in_intimate_for_core),
        )
        res["choices"] = hybrid_choices
        res["next_choices"] = hybrid_choices
        res["_hybrid_choices_built"] = True

    if _pre_turn_site_items_by_uid and isinstance(res, dict):
        res["_site_items_gained"] = _pre_turn_site_items_by_uid

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
                    await adb(db.update_session, session["id"], **db_updates)
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
