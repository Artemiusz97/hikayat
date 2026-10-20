from .constants import *
import mechanics.narrative.event_handlers
from mechanics.narrative.events import bus, LocationChangedEvent, NPCSpawnedEvent, NPCStatusChangedEvent, ItemGiftedEvent, ItemGainedEvent, FactionLeadershipChangedEvent, QuestCompletedEvent
import json
from mechanics.social.factions import (
    guess_hierarchy_template,
    generate_procedural_leadership_roster,
    promote_player_in_roster,
    get_rank_title,
)
import re
import logging
log = logging.getLogger(__name__)
logger = log
import game_engine

from game_engine.core import CONFESSION_KEYWORDS, NPC_ORAL_RECEIVE_KEYWORDS, NPC_ORAL_GIVE_KEYWORDS, NPC_MANUAL_RECEIVE_KEYWORDS, NPC_MANUAL_GIVE_KEYWORDS, NPC_ANAL_RECEIVE_KEYWORDS, NPC_ANAL_GIVE_KEYWORDS, ANAL_KEYWORDS, INTERCOURSE_KEYWORDS, KISS_KEYWORDS, DATE_KEYWORDS, ROMANCE_KEYWORDS
def _evaluate_npc_milestones(
    npc_name: str,
    app_dict: dict,
    track: str,
    milestone_ev: str,
    custom_summary: str | None,
    intercourse_exp: str,
    oral_exp: str,
    actions: list,
    narrative_text: str,
    overall_check_success: bool,
    is_player_romantic_action: bool,
    is_player_intimate_action: bool,
    is_player_oral_action: bool,
    is_player_intercourse_action: bool,
    is_player_confession_action: bool,
    is_player_affection_action: bool,
    affection_target_npc: str | None,
    gift_target_npc: str | None,
    gift_item_name: str | None,
    confession_target_npc: str | None,
    first_char_name: str,
    session: dict | None = None,
    single_update: bool = False,
    combined_check_text: str | None = None,
) -> tuple[str | None, str, str, str, str, bool, int]:
    """Evaluates intimate and romantic milestones for an NPC.
    Returns: (new_mem, current_intercourse, current_oral, current_manual, track, is_intimate_act, delta_boost)
    """
    from mechanics.social.persona import (
        transition_intercourse_experience,
        transition_oral_experience,
        transition_manual_experience,
        transition_anal_experience,
        format_milestone_memory,
        VALID_MILESTONE_EVENTS,
    )
    from mechanics.social.relationships import is_romantic_confession_intent

    current_intercourse = intercourse_exp or app_dict.get("intercourse_experience") or "virgin"
    current_oral = oral_exp or app_dict.get("oral_experience") or "inexperienced"
    current_manual = app_dict.get("manual_experience", "inexperienced")
    current_anal = app_dict.get("anal_experience", "inexperienced")
    is_intimate_act = False
    new_mem = None
    delta_boost = 0

    import namegen
    npc_low = npc_name.lower().strip() if npc_name else ""
    npc_fst = npc_low.split()[0] if npc_low else ""
    npc_gvn = namegen.extract_first_and_last_name(npc_name)[0].lower().strip() if npc_name else ""
    npc_tokens = {t for t in (npc_fst, npc_gvn) if t and t not in namegen.NAME_PARTICLES_AND_HONORIFICS}

    from mechanics.world.mobility import get_session_dialogue_partners
    from mechanics.social.intimate_excitement import (
        is_actively_targeted_in_action,
        scope_text_to_partner,
        _normalize_partner_pronouns,
    )
    from game_engine.core import (
        PLAYER_ROMANTIC_ACTION_KEYWORDS,
        PLAYER_INTIMATE_ACTION_KEYWORDS,
        PLAYER_ORAL_ACTION_KEYWORDS,
        PLAYER_INTERCOURSE_ACTION_KEYWORDS,
        matches_keyword_boundary,
    )

    sess_dps = get_session_dialogue_partners(session) if isinstance(session, dict) else []
    other_dp_names = [
        dp for dp in sess_dps
        if dp and dp.lower().strip() != npc_low and not (npc_tokens & {(dp.lower().split() or [""])[0], namegen.extract_first_and_last_name(dp)[0].lower().strip()})
    ]
    raw_actions_text = " ".join(str(a.get("label", "")) for a in (actions or []))
    npc_active_in_act = is_actively_targeted_in_action(npc_name, raw_actions_text) if npc_name else False
    other_active_in_act = any(is_actively_targeted_in_action(op, raw_actions_text) for op in other_dp_names)

    if other_dp_names and other_active_in_act:
        if npc_active_in_act:
            scoped_act_raw = scope_text_to_partner(raw_actions_text, npc_name, other_dp_names).lower()
            scoped_nar_raw = scope_text_to_partner(narrative_text or "", npc_name, other_dp_names).lower()
            scoped_act_norm = _normalize_partner_pronouns(scoped_act_raw, npc_name, app_dict)
            scoped_nar_norm = _normalize_partner_pronouns(scoped_nar_raw, npc_name, app_dict)
            scoped_act_str = f"{scoped_act_raw} {scoped_act_norm}".strip() if scoped_act_norm and scoped_act_norm != scoped_act_raw else scoped_act_raw
            scoped_nar_str = f"{scoped_nar_raw} {scoped_nar_norm}".strip() if scoped_nar_norm and scoped_nar_norm != scoped_nar_raw else scoped_nar_raw

            is_oral_scoped = matches_keyword_boundary(scoped_act_str, PLAYER_ORAL_ACTION_KEYWORDS, allow_negated=False)
            is_anal_scoped = matches_keyword_boundary(scoped_act_str, ("anal", "ass", "pegged", "pegging", "backdoor"), allow_negated=False)
            has_exp_pen_scoped = matches_keyword_boundary(scoped_act_str, ("dick", "cock", "shaft", "penis", "have sex", "make love", "penetrate", "fuck", "creampie", "breed"), allow_negated=False)
            is_intercourse_scoped = matches_keyword_boundary(scoped_act_str, PLAYER_INTERCOURSE_ACTION_KEYWORDS, allow_negated=False) and (
                (not is_oral_scoped and not is_anal_scoped) or (has_exp_pen_scoped and not is_anal_scoped)
            )
            is_intimate_scoped = (
                is_intercourse_scoped
                or is_oral_scoped
                or is_anal_scoped
                or matches_keyword_boundary(scoped_act_str, PLAYER_INTIMATE_ACTION_KEYWORDS, allow_negated=False)
            )
            is_romantic_scoped = matches_keyword_boundary(scoped_act_str, PLAYER_ROMANTIC_ACTION_KEYWORDS, allow_negated=False)

            is_player_intercourse_action = is_intercourse_scoped
            is_player_oral_action = is_oral_scoped
            is_player_intimate_action = is_intimate_scoped
            is_player_romantic_action = is_romantic_scoped or is_player_confession_action

            if not is_intimate_scoped and (
                matches_keyword_boundary(raw_actions_text.lower(), PLAYER_INTERCOURSE_ACTION_KEYWORDS, allow_negated=False)
                or matches_keyword_boundary(raw_actions_text.lower(), PLAYER_ORAL_ACTION_KEYWORDS, allow_negated=False)
                or matches_keyword_boundary(raw_actions_text.lower(), PLAYER_INTIMATE_ACTION_KEYWORDS, allow_negated=False)
            ):
                combined_check_text = scoped_act_str
            else:
                combined_check_text = f"{scoped_act_str} {scoped_nar_str}".strip()
        else:
            is_player_intercourse_action = False
            is_player_oral_action = False
            is_player_intimate_action = False
            is_player_romantic_action = False
            combined_check_text = ""
    elif combined_check_text is None:
        raw_comb = (
            raw_actions_text + " " + (narrative_text or "")
        ).lower()
        norm_comb = _normalize_partner_pronouns(raw_comb, npc_name, app_dict) if npc_name else ""
        combined_check_text = f"{raw_comb} {norm_comb}".strip() if norm_comb and norm_comb != raw_comb else raw_comb

    # Pre-evaluate cues once to avoid redundant scans across large keyword tuples
    has_rec_cues = False
    has_give_cues = False
    has_m_rec = False
    has_m_give = False
    has_a_rec = False
    has_a_give = False
    has_intercourse = False
    has_kiss = False
    has_date = False
    has_romance = False

    if overall_check_success:
        has_rec_cues = any(kw in combined_check_text for kw in NPC_ORAL_RECEIVE_KEYWORDS)
        has_give_cues = any(kw in combined_check_text for kw in NPC_ORAL_GIVE_KEYWORDS)
        has_m_rec = any(kw in combined_check_text for kw in NPC_MANUAL_RECEIVE_KEYWORDS)
        has_m_give = any(kw in combined_check_text for kw in NPC_MANUAL_GIVE_KEYWORDS)
        has_a_rec = any(kw in combined_check_text for kw in NPC_ANAL_RECEIVE_KEYWORDS)
        has_a_give = any(kw in combined_check_text for kw in NPC_ANAL_GIVE_KEYWORDS)
        has_intercourse = any(kw in combined_check_text for kw in INTERCOURSE_KEYWORDS)
        has_kiss = any(kw in combined_check_text for kw in KISS_KEYWORDS)
        has_date = any(kw in combined_check_text for kw in DATE_KEYWORDS)
        has_romance = any(kw in combined_check_text for kw in ROMANCE_KEYWORDS)

    def _reveal_intimacy(act_type: str):
        nonlocal is_intimate_act
        is_intimate_act = True
        
        # Always reveal demeanor and dynamic when any intimate/romantic act occurs
        app_dict["demeanor_revealed"] = True
        app_dict["dynamic_revealed"] = True
        
        if act_type in ("confession", "kiss", "first_kiss", "date"):
            # Purely romantic/affectionate acts do not reveal explicit sexual tracks
            return
            
        # For actual physical intimacy, reveal sensitivities and general explicit unlock
        app_dict["turn_ons_revealed"] = True
        app_dict["sensitive_spots_revealed"] = True
        app_dict["act_preferences_revealed"] = True
        app_dict["intimate_revealed"] = True
        
        # Reveal tracks progressively based on the act
        if act_type == "intercourse":
            app_dict["intercourse_revealed"] = True
            app_dict["oral_revealed"] = True
            app_dict["manual_revealed"] = True
            app_dict["fetishes_revealed"] = True
            app_dict["underwear_revealed"] = True
            app_dict["intimate_revealed"] = True # Full explicit profile unlock
        elif act_type in ("oral_give", "oral_receive"):
            app_dict["oral_revealed"] = True
            app_dict["underwear_revealed"] = True
        elif act_type in ("manual_give", "manual_receive"):
            app_dict["manual_revealed"] = True
        elif act_type in ("anal_give", "anal_receive", "anal"):
            app_dict["anal_revealed"] = True
            app_dict["underwear_revealed"] = True

    is_session_dp = bool(session and game_engine.is_dialogue_partner(npc_name, session=session))
    explicit_confession_target_match = bool(
        (confession_target_npc and (npc_low == confession_target_npc.lower().strip() or npc_fst == (confession_target_npc.lower().split() or [""])[0]))
        or any(
            (is_romantic_confession_intent(str(a.get("label", ""))) or any(kw in str(a.get("label", "")).lower() for kw in CONFESSION_KEYWORDS))
            and (npc_low in str(a.get("label", "")).lower() or (len(npc_fst) >= 3 and bool(re.search(rf"\b{re.escape(npc_fst)}\b", str(a.get("label", "")).lower()))))
            for a in actions
        )
    )
    has_other_confession_target = bool(
        confession_target_npc and not explicit_confession_target_match
    )
    is_npc_target_of_confession = (
        explicit_confession_target_match
        or (not has_other_confession_target and is_session_dp and is_player_confession_action)
        or (not has_other_confession_target and session is None and is_player_confession_action)
    )

    # Tier 1: Structured LLM Milestone Event Processing
    if overall_check_success and milestone_ev in VALID_MILESTONE_EVENTS and milestone_ev != "none":
        if milestone_ev in ("oral_give", "oral_receive"):
            if has_rec_cues and not has_give_cues:
                milestone_ev = "oral_receive"
            elif has_give_cues and not has_rec_cues:
                milestone_ev = "oral_give"
        elif milestone_ev in ("manual_give", "manual_receive"):
            if has_m_rec and not has_m_give:
                milestone_ev = "manual_receive"
            elif has_m_give and not has_m_rec:
                milestone_ev = "manual_give"
        elif milestone_ev in ("anal_give", "anal_receive"):
            if has_a_rec and not has_a_give:
                milestone_ev = "anal_receive"
            elif has_a_give and not has_a_rec:
                milestone_ev = "anal_give"
        elif milestone_ev == "intercourse":
            if (is_player_oral_action or has_rec_cues or has_give_cues) and not is_player_intercourse_action:
                if has_give_cues and not has_rec_cues:
                    milestone_ev = "oral_give"
                else:
                    milestone_ev = "oral_receive"
            elif (has_a_rec or has_a_give) and not is_player_intercourse_action:
                if has_a_give and not has_a_rec:
                    milestone_ev = "anal_give"
                else:
                    milestone_ev = "anal_receive"

        if milestone_ev == "intercourse":
            current_intercourse = "non_virgin"
            app_dict["had_first_time_with_player"] = True
            _reveal_intimacy("intercourse")
            new_mem = format_milestone_memory("intercourse", first_char_name, custom_summary)
        elif milestone_ev == "oral_give":
            current_oral = transition_oral_experience(current_oral, "oral_give")
            _reveal_intimacy("oral_give")
            new_mem = format_milestone_memory("oral_give", first_char_name, custom_summary)
        elif milestone_ev == "oral_receive":
            current_oral = transition_oral_experience(current_oral, "oral_receive")
            _reveal_intimacy("oral_receive")
            new_mem = format_milestone_memory("oral_receive", first_char_name, custom_summary)
        elif milestone_ev == "manual_give":
            current_manual = transition_manual_experience(current_manual, "manual_give")
            _reveal_intimacy("manual_give")
            new_mem = format_milestone_memory("manual_give", first_char_name, custom_summary)
        elif milestone_ev == "manual_receive":
            current_manual = transition_manual_experience(current_manual, "manual_receive")
            _reveal_intimacy("manual_receive")
            new_mem = format_milestone_memory("manual_receive", first_char_name, custom_summary)
        elif milestone_ev == "anal_give":
            current_anal = transition_anal_experience(current_anal, "anal_give")
            _reveal_intimacy("anal_give")
            new_mem = format_milestone_memory("anal_give", first_char_name, custom_summary)
        elif milestone_ev == "anal_receive":
            current_anal = transition_anal_experience(current_anal, "anal_receive")
            _reveal_intimacy("anal_receive")
            new_mem = format_milestone_memory("anal_receive", first_char_name, custom_summary)
        elif milestone_ev == "anal":
            current_anal = transition_anal_experience(current_anal, "anal_receive")
            _reveal_intimacy("anal_receive")
            new_mem = format_milestone_memory("anal", first_char_name, custom_summary)
        elif milestone_ev in ("first_kiss", "kiss"):
            _reveal_intimacy(milestone_ev)
            new_mem = format_milestone_memory(milestone_ev, first_char_name, custom_summary)
        elif milestone_ev == "confession" and not has_other_confession_target:
            new_mem = format_milestone_memory("confession", first_char_name, custom_summary)
            _reveal_intimacy("confession")
            app_dict["demeanor_revealed"] = True
            if is_npc_target_of_confession and overall_check_success:
                track = "romantic"
        elif milestone_ev == "date":
            new_mem = format_milestone_memory("date", first_char_name, custom_summary)
            if overall_check_success:
                track = "romantic"

    # Tier 2: Secondary Engine Safety Net (Scoped to Target/Active Scene NPC)
    is_action_match = (
        npc_active_in_act
        if (other_dp_names and other_active_in_act)
        else any(
            (npc_low in str(a.get("label", "")).lower() or (len(npc_fst) >= 3 and npc_fst in str(a.get("label", "")).lower()))
            for a in actions
        )
    )
    is_npc_target_of_action = (
        is_action_match
        if (other_dp_names and other_active_in_act)
        else (is_action_match or is_session_dp or (session is None) or single_update)
    )

    if not new_mem and overall_check_success:
        is_pure_oral = (is_player_oral_action or has_rec_cues or has_give_cues) and not is_player_intercourse_action
        is_pure_anal = (has_a_rec or has_a_give) and not is_player_intercourse_action
        if is_npc_target_of_action and (is_player_intercourse_action or (has_intercourse and not is_pure_oral and not is_pure_anal)):
            current_intercourse = "non_virgin"
            app_dict["had_first_time_with_player"] = True
            new_mem = format_milestone_memory("intercourse", first_char_name, custom_summary)
            _reveal_intimacy("intercourse")
        elif is_npc_target_of_action and ((is_player_intimate_action or is_player_oral_action or has_rec_cues) and has_rec_cues):
            current_oral = transition_oral_experience(current_oral, "oral_receive")
            new_mem = format_milestone_memory("oral_receive", first_char_name, custom_summary)
            _reveal_intimacy("oral_receive")
        elif is_npc_target_of_action and ((is_player_intimate_action or is_player_oral_action or has_give_cues) and has_give_cues):
            current_oral = transition_oral_experience(current_oral, "oral_give")
            new_mem = format_milestone_memory("oral_give", first_char_name, custom_summary)
            _reveal_intimacy("oral_give")
        elif is_npc_target_of_action and has_a_rec:
            current_anal = transition_anal_experience(current_anal, "anal_receive")
            new_mem = format_milestone_memory("anal_receive", first_char_name, custom_summary)
            _reveal_intimacy("anal_receive")
        elif is_npc_target_of_action and has_a_give:
            current_anal = transition_anal_experience(current_anal, "anal_give")
            new_mem = format_milestone_memory("anal_give", first_char_name, custom_summary)
            _reveal_intimacy("anal_give")
        elif is_npc_target_of_action and has_m_rec:
            current_manual = transition_manual_experience(current_manual, "manual_receive")
            new_mem = format_milestone_memory("manual_receive", first_char_name, custom_summary)
            _reveal_intimacy("manual_receive")
        elif is_npc_target_of_action and has_m_give:
            current_manual = transition_manual_experience(current_manual, "manual_give")
            new_mem = format_milestone_memory("manual_give", first_char_name, custom_summary)
            _reveal_intimacy("manual_give")
        elif ((is_player_romantic_action and is_npc_target_of_action) or milestone_ev in ("first_kiss", "kiss")) and has_kiss:
            _reveal_intimacy(milestone_ev if milestone_ev in ("first_kiss", "kiss") else "kiss")
            new_mem = format_milestone_memory(milestone_ev if milestone_ev in ("first_kiss", "kiss") else "kiss", first_char_name, custom_summary)
        elif is_npc_target_of_confession or (milestone_ev == "confession" and is_player_confession_action and not has_other_confession_target):
            new_mem = format_milestone_memory("confession", first_char_name, custom_summary)
            _reveal_intimacy("confession")
            app_dict["demeanor_revealed"] = True
            if overall_check_success:
                track = "romantic"
        elif ((is_player_romantic_action and is_npc_target_of_action) or milestone_ev == "date") and has_date:
            new_mem = format_milestone_memory("date", first_char_name, custom_summary)
            if overall_check_success:
                track = "romantic"
        elif is_player_affection_action and (affection_target_npc and (npc_low == affection_target_npc.lower().strip() or npc_fst == (affection_target_npc.lower().split() or [""])[0])):
            new_mem = format_milestone_memory("milestone", first_char_name, custom_summary) if custom_summary else f"Shared a tender, affectionate moment with {first_char_name}"
            delta_boost = 3
        elif gift_target_npc and (npc_low == gift_target_npc.lower().strip() or npc_fst == (gift_target_npc.lower().split() or [""])[0]):
            gift_label = gift_item_name or "a gift"
            new_mem = format_milestone_memory("milestone", first_char_name, custom_summary) if custom_summary else f"Received {gift_label} as a thoughtful gift from {first_char_name}"
        elif custom_summary:
            new_mem = format_milestone_memory("milestone", first_char_name, custom_summary)
        elif is_player_romantic_action and is_npc_target_of_action and has_romance:
            new_mem = f"Romantic milestone shared with {first_char_name}"

        if (is_npc_target_of_confession or (milestone_ev == "confession" and is_player_confession_action)) and overall_check_success:
            track = "romantic"

    app_dict["anal_experience"] = current_anal
    return new_mem, current_intercourse, current_oral, current_manual, track, is_intimate_act, delta_boost

def _reduce_quests_and_waypoints(session_id: int, session: dict, party_uids: list, outcome: dict, actions: list, items_gained_by_user: dict):
    """Extracted Phase 2B Reducer for Quest and Waypoint Updates."""
    import db, game_engine
      # Process quest_updates array from OUTCOME_SCHEMA (preserving any pre-turn deterministic rewards/sub-quests)
    quest_reward_notices = list(outcome.get("_quest_reward_notices") or [])
    completed_sub_quests = list(outcome.get("_completed_sub_quests") or [])
    newly_discovered_clues = []
    already_claimed_qids = {
        str(rn.get("quest_id"))
        for rn in quest_reward_notices
        if isinstance(rn, dict) and rn.get("quest_id")
    }
    updated_quest_ids = set(already_claimed_qids)
    for qu in outcome.get("quest_updates") or []:
        if not isinstance(qu, dict):
            continue
        qid = qu.get("quest_id")
        if qid:
            updated_quest_ids.add(str(qid))
            if str(qid) in already_claimed_qids:
                continue
        notice = game_engine.apply_quest_update(session_id, qu, party_user_ids=party_uids, outcome=outcome, actions=actions)
        if notice:
            if notice.get("claimed"):
                quest_reward_notices.append(notice)
            if notice.get("newly_completed_sub_quests"):
                completed_sub_quests.extend(notice["newly_completed_sub_quests"])
            if notice.get("newly_discovered_clue"):
                newly_discovered_clues.append(notice["newly_discovered_clue"])
  
    # Deterministic fallback for active Story Quest if LLM omitted it from quest_updates
    active_sq = db.get_active_story_quest(session_id)
    if active_sq and active_sq.get("quest_id") not in updated_quest_ids:
        sub_objs = active_sq.get("sub_objectives", [])
        all_sub_done = bool(sub_objs and all(so.get("completed") for so in sub_objs if isinstance(so, dict)))
        action_is_climax = any(
            bool(a.get("is_climax_action")) or
            str(a.get("contract_type", "")).lower() == "climax" or
            "[story climax]" in str(a.get("label", "")).lower() or
            "[climax]" in str(a.get("label", "")).lower() or
            "story climax" in str(a.get("label", "")).lower() or
            "⚡" in str(a.get("label", ""))
            for a in (actions or [])
        )
        action_succeeded = any(
            (hasattr(a.get("check"), "succeeded") and a["check"].succeeded) or
            (isinstance(a.get("check"), dict) and a["check"].get("succeeded")) or
            (a.get("stat") in ("NONE", "FREE") or a.get("requirement", 0) <= 0)
            for a in (actions or [])
        )
        if all_sub_done and action_is_climax and action_succeeded:
            synth_update = {
                "quest_id": active_sq["quest_id"],
                "title": active_sq["title"],
                "status": "Completed",
                "sub_objectives": sub_objs
            }
            notice = game_engine.apply_quest_update(session_id, synth_update, party_user_ids=party_uids, outcome=outcome, actions=actions)
            if notice and notice.get("claimed"):
                quest_reward_notices.append(notice)
  
    if quest_reward_notices:
        outcome["_quest_reward_notices"] = quest_reward_notices
    if completed_sub_quests:
        outcome["_completed_sub_quests"] = completed_sub_quests
    is_combat = bool(outcome and (outcome.get("_combat_log") or outcome.get("_enemy_attack_notice") or game_engine.get_active_enemies(outcome)))
    if newly_discovered_clues and not is_combat:
        outcome["_newly_discovered_clue"] = newly_discovered_clues[0]
    else:
        outcome.pop("_newly_discovered_clue", None)
  
    for rn in quest_reward_notices:
        ritem = rn.get("item")
        if ritem:
            already_granted = bool(rn.get("_item_granted_in_db"))
            for uid in party_uids:
                if already_granted:
                    if ritem not in items_gained_by_user.get(uid, []):
                        items_gained_by_user.setdefault(uid, []).append(ritem)
                else:
                    added_id = db.add_item(uid, ritem, "Quest Reward", "Reward from completed objective")
                    if added_id is not None:
                        items_gained_by_user.setdefault(uid, []).append(ritem)
                    else:
                        items_gained_by_user.setdefault(uid, []).append(f"{ritem} (Lost: Inventory Full!)")
            rn["_item_granted_in_db"] = True

def _reduce_vitals_and_inventory(session_id: int, session: dict, party: list, outcome: dict, mp_already_spent: dict, scen_key: str, is_combat: bool, items_gained_by_user: dict):
    """Extracted Phase 2B Reducer for Character HP/MP, Status Effects, and Loot."""
    import db, re
    from mechanics.system.phone import scenario_has_smartphone
    name_to_char = {char['name'].lower(): char for char, _ in party}
    for co in outcome.get("character_outcomes", []) or []:
      if not isinstance(co, dict):
          continue  # Guard: skip malformed string/non-dict LLM entries
      char = name_to_char.get(str(co.get("name", "")).lower())
      if not char:
          continue
      user_id = char["user_id"]
      try:
          hp_delta = int(co.get("hp_change", 0))
      except (ValueError, TypeError):
          hp_delta = 0
          
      if isinstance(mp_already_spent, bool) or mp_already_spent is None:
          mp_already_spent = {}
          
      spent = mp_already_spent.get(user_id, 0)
      try:
          raw_mp = int(co.get("mp_change", 0))
          if raw_mp <= 0:
              mp_delta = min(0, raw_mp + spent)
          else:
              mp_delta = raw_mp
      except (ValueError, TypeError):
          mp_delta = 0
      try:
          gold_delta = int(co.get("gold_change", 0))
      except (ValueError, TypeError):
          gold_delta = 0
          
      try:
          temp_hp_delta = int(co.get("temp_hp_change", 0))
      except (ValueError, TypeError):
          temp_hp_delta = 0
          
      import scenario_data
      if not is_combat and scenario_data.is_non_combat_scenario(scen_key):
          if hp_delta < 0:
              hp_delta = 0
          if temp_hp_delta < 0:
              temp_hp_delta = 0

      db.apply_hp_mp_delta(user_id, hp_delta, mp_delta, gold_delta, temp_hp_delta)
  
      gained = co.get("items_gained", []) or []
      for item_name in gained:
          is_media = any(k in item_name.lower() for k in ("photo", "selfie", "video", "snapshot", "recording", "clip"))
          if is_media and scenario_has_smartphone(scen_key):
              from mechanics.combat.items import create_digital_media_item
              m_type = "video" if "video" in item_name.lower() or "clip" in item_name.lower() else "photo"
              caption = outcome.get("outcome_narrative", "").split("\n")[0][:250] or item_name
              added_id = create_digital_media_item(user_id, item_name, m_type, caption, subject=session.get("current_location", "Local Area"), tags=["misc", "digital", "story"])
              gain_lbl = item_name
          else:
              from mechanics.combat.items import classify_and_enrich_ad_hoc_item
              enriched = classify_and_enrich_ad_hoc_item(item_name, scen_key)
              gain_lbl = enriched["name"]
              added_id = db.add_item(
                  user_id=user_id,
                  name=enriched["name"],
                  item_type=enriched["item_type"],
                  effect=enriched["effect"],
                  slot_cost=enriched.get("slot_cost", 1)
              )
          if added_id is not None:
              items_gained_by_user.setdefault(user_id, []).append(gain_lbl)
          else:
              items_gained_by_user.setdefault(user_id, []).append(f"{gain_lbl} (Lost: Inventory Full!)")
      for item_name in co.get("items_lost", []) or []:
          db.remove_item_by_name(user_id, item_name)
  
      status_raw = co.get("status_effects", []) or []
      if not isinstance(status_raw, list):
          status_raw = [status_raw] if status_raw else []

      # Preserve active timed status effects on character (like Aroused [N turns]) already ticked
      char_status = char.get("status_effects", []) if isinstance(char, dict) else []
      if isinstance(char_status, str):
          import json
          try:
              char_status = json.loads(char_status)
          except Exception:
              char_status = [char_status] if char_status else []
      elif not isinstance(char_status, list):
          char_status = []

      for cs in char_status:
          if isinstance(cs, str) and cs.strip():
              if re.search(r"\[\d+\s*(?:turns?|min)\]", cs, re.IGNORECASE):
                  base_name = re.sub(r"\s*\[\d+\s*(?:turns?|min)\]", "", cs).strip().lower()
                  if not any(base_name in str(s).lower() for s in status_raw):
                      status_raw.append(cs)

      from character_data import sanitize_status_effects
      cleaned_status = sanitize_status_effects(status_raw)
      if not is_combat:
          # Clear temporary combat turn buffs when transitioning outside combat
          cleaned_status = [
              s for s in cleaned_status
              if not any(k in s for k in ("Iron Skin", "Aegis Warding", "Combat Booster", "Quickstep", "DT]", "DR]", "% ATK]", "% EVA]"))
              and not (re.search(r"\[\d+\s*turns?\]", s, re.IGNORECASE) and "aroused" not in s.lower())
          ]

      # Refractory & Climax Cleanse: If in refractory recovery or spent, purge lingering Aroused and Breathless
      try:
          from mechanics.social.intimate_excitement import is_in_refractory_cooldown, format_partner_recovery_status_tag
          sess_row = session if isinstance(session, dict) and session else (db.get_session(session_id) if session_id else {})
          p_state = (db.get_session_physical_state(session_id) if session_id else None) or (sess_row.get("physical_state") if isinstance(sess_row, dict) else {})
          in_refr_check, refr_mins_check = is_in_refractory_cooldown(sess_row or {}, p_state or {})
          p_exc = (p_state or {}).get("excitement") if isinstance(p_state, dict) else {}
          p_climax_st = (p_state or {}).get("climax_state") if isinstance(p_state, dict) else {}
          lead_user_id = (party[0][0]["user_id"] if isinstance(party[0], (tuple, list)) else party[0].get("user_id")) if party else None
          is_lead_player = (user_id == lead_user_id) if lead_user_id is not None else True
          if is_lead_player:
              if isinstance(p_exc, dict) and p_exc.get("player_in_refractory") is not None:
                  char_climaxed_flag = bool(p_exc.get("player_in_refractory"))
              else:
                  char_climaxed_flag = p_climax_st.get("player_climaxed", True) if isinstance(p_climax_st, dict) and p_climax_st else True
          else:
              part_climax_map = {
                  **(p_climax_st.get("partner_climaxes") or {}),
                  **(p_exc.get("refractory_partners") or {})
              }
              c_name = char.get("name", "") if isinstance(char, dict) else ""
              from mechanics.social.intimate_excitement import _match_actor_key
              m_k = _match_actor_key(c_name, part_climax_map) if part_climax_map else ""
              char_climaxed_flag = bool(part_climax_map.get(m_k or c_name, False) or p_climax_st.get("partner_climaxed", False))

          if in_refr_check and refr_mins_check > 0 and char_climaxed_flag:
              char_gen = char.get("gender", "Male") if isinstance(char, dict) else "Male"
              refr_tag = format_partner_recovery_status_tag(refr_mins_check, char_gen)
              cleaned_status = [
                  s for s in cleaned_status
                  if not any(k in str(s).lower() for k in ("aroused", "breathless", "spent"))
                  and not any(k in str(s).lower() for k in ("refractory", "satisfied"))
              ]
              cleaned_status.append(refr_tag)
          else:
              cleaned_status = [
                  s for s in cleaned_status
                  if not any(k in str(s).lower() for k in ("refractory", "satisfied"))
              ]
      except Exception:
          pass

      if any(k in s.lower() for s in (status_raw or []) + (cleaned_status or []) for k in ("recovering", "exhausted")):
          # Character was revived or recovering from party defeat: purge trauma/combat debuffs and turn counters
          cleaned_status = [
              s for s in cleaned_status
              if not any(k in s.lower() for k in ("bleed", "poison", "burn", "torn", "scorched", "stun", "frozen", "shock", "bruised"))
              and not re.search(r"\[\d+\s*turns?\]", s, re.IGNORECASE)
          ]
          if not any("exhausted" in s.lower() or "recovering" in s.lower() for s in cleaned_status):
              cleaned_status.append("Exhausted / Recovering")
      db.set_status_effects(user_id, cleaned_status)
      if isinstance(char, dict):
          char["status_effects"] = list(cleaned_status)
      co["status_effects"] = list(cleaned_status)
      if not is_combat:
          db.apply_turn_regen(user_id)

def _reduce_factions(session_id: int, session: dict, outcome: dict, party: list, first_char_id: int):
    """Extracted Phase 2B Reducer for Faction Discoveries and Promotions."""
    import db, game_engine
    from scenario_data import is_mechanic_enabled
    _faction_scen_key = session.get("scenario", "fantasy") if session else "fantasy"
    from mechanics.social.factions import infer_default_hq_location
  
    faction_updates_list = [
        dict(f) for f in (outcome.get("faction_updates", []) or [])
        if isinstance(f, dict)
    ]
  
    # Auto-detect faction discovery when player interacts with an affiliated contact
    for ru in outcome.get("relationship_updates", []) or []:
        if not isinstance(ru, dict):
            continue
        c_name = str(ru.get("name") or ru.get("npc_name") or "").strip()
        if not c_name:
            continue
        c = db.get_contact(session_id, c_name, first_char_id) or db.get_contact(session_id, c_name.lower().replace(" ", "_"))
        if c:
            b = c.get("basic_info") or {}
            c_fac = str(b.get("faction") or b.get("faction_affiliation") or b.get("club") or c.get("faction") or "").strip()
            if c_fac and c_fac.lower() not in ("none", "unaligned", ""):
                existing_fnames = [str(f.get("faction_name") or f.get("name") or "").lower() for f in faction_updates_list]
                if c_fac.lower() in existing_fnames:
                    continue
                old_score = int(c.get("relationship_score", c.get("score", 0)) or 0)
                ru_delta = int(ru.get("delta_score", 0) or 0)
                new_score = old_score + ru_delta
  
                # One-time Friend milestone endorsement (+5 Rep when crossing 30 Affinity)
                if old_score < 30 and new_score >= 30:
                    if c_fac.lower() not in existing_fnames:
                        faction_updates_list.append({
                            "faction_name": c_fac,
                            "delta_score": 5,
                            "notes": f"Milestone endorsement from {c_name} (Reached Friend status)."
                        })
                elif not db.get_faction(session_id, c_fac):
                    # Auto-discover unseeded faction at Neutral 0 Rep
                    if c_fac.lower() not in existing_fnames:
                        faction_updates_list.append({
                            "faction_name": c_fac,
                            "delta_score": 0,
                            "notes": f"Introduced via {c_name}."
                        })
  
    newly_discovered_factions = []
  
    for fac in faction_updates_list:
        fname = fac.get("faction_name") or fac.get("name")
        if not fname:
            continue
        delta = int(fac.get("delta_score") or 0)
        # Clamp delta to -20/+20 to prevent LLM exploits
        delta = max(-20, min(20, delta))
  
        proper_template = guess_hierarchy_template(fname, _faction_scen_key)
        faction_row = db.get_faction(session_id, fname)
        is_brand_new = (faction_row is None)
  
        if faction_row:
            current_tmpl = faction_row.get("hierarchy_template")
            if current_tmpl == "guild" and proper_template != "guild":
                template = proper_template
            else:
                template = current_tmpl or proper_template
            hq_loc = faction_row.get("hq_location_id") or infer_default_hq_location(fname, _faction_scen_key)
        else:
            template = proper_template
            hq_loc = fac.get("hq_location_id") or infer_default_hq_location(fname, _faction_scen_key)
  
        # Provision dedicated Tier 2 HQ location and Tier 3 sub-areas in SQLite
        from mechanics.world.locations import provision_faction_hq_tier2_location
        hq_loc = provision_faction_hq_tier2_location(session_id, fname, _faction_scen_key, hq_loc)
  
        if is_brand_new:
            newly_discovered_factions.append({
                "name": fname,
                "hq": hq_loc,
                "template": template
            })
  
        upserted = db.upsert_faction(
            session_id=session_id,
            name=fname,
            delta_score=delta,
            notes=fac.get("notes", ""),
            hierarchy_template=template,
            category=template,
            hq_location_id=hq_loc,
        )
        # Lazy leadership roster generation on first discovery or roster upgrade
        faction_row = db.get_faction(session_id, upserted.get("faction_id", fname))
        if faction_row:
            existing_roster = faction_row.get("leadership_roster") or []
            if not existing_roster:
                roster = generate_procedural_leadership_roster(fname, template, _faction_scen_key)
                db.upsert_faction(
                    session_id=session_id,
                    name=fname,
                    delta_score=0,
                    hierarchy_template=template,
                    leadership_roster=roster,
                    category=template,
                    hq_location_id=hq_loc,
                )
            elif faction_row.get("hierarchy_template") != template or (existing_roster and existing_roster[0].get("title") == "Guildmaster" and template != "guild"):
                # Update existing roster titles to match new template
                for r in existing_roster:
                    r["title"] = get_rank_title(template, r.get("rank", 1))
                db.upsert_faction(
                    session_id=session_id,
                    name=fname,
                    delta_score=0,
                    hierarchy_template=template,
                    leadership_roster=existing_roster,
                    category=template,
                )
        # -----------------------------------------------------------------------
        # Diplomatic Ripple: propagate reputation changes to rivals and allies.
        # Guarded by `_is_ripple=True` on secondary updates to prevent cascades.
        # -----------------------------------------------------------------------
        if delta != 0 and not fac.get("_is_ripple"):
            # Re-fetch the freshest faction row (post-upsert) to get allies/rivals
            updated_fac_row = db.get_faction(session_id, fname)
            if updated_fac_row:
                rival_ids  = updated_fac_row.get("rival_faction_ids", []) or []
                ally_ids   = updated_fac_row.get("allied_faction_ids", []) or []
  
                if delta > 0:
                    # Gain with A → lose with rivals (30%), gain with allies (30%)
                    rival_delta = -max(1, round(abs(delta) * 0.30))
                    ally_delta  =  max(1, round(abs(delta) * 0.30))
                else:
                    # Lose with A → gain small amount with rivals (20%)
                    rival_delta = max(1, round(abs(delta) * 0.20))
                    ally_delta  = 0   # suffering doesn't automatically help allies
  
                for rid in rival_ids:
                    rival = db.get_faction(session_id, rid)
                    if rival:
                        db.upsert_faction(
                            session_id=session_id,
                            name=rival["name"],
                            delta_score=rival_delta,
                        )
  
                for aid in ally_ids:
                    ally = db.get_faction(session_id, aid)
                    if ally and ally_delta != 0:
                        db.upsert_faction(
                            session_id=session_id,
                            name=ally["name"],
                            delta_score=ally_delta,
                        )
  
    outcome["faction_updates"] = faction_updates_list
    if newly_discovered_factions:
        outcome["_newly_discovered_factions"] = newly_discovered_factions
  
    if session_id and is_mechanic_enabled(_faction_scen_key, "faction_reputation"):
        try:
            from mechanics.social.factions import sync_faction_rosters_with_contacts
            sync_faction_rosters_with_contacts(session_id)
        except Exception:
            pass
  
    # Handle faction promotion result from pre-turn engine or LLM
    faction_promotion_result = outcome.get("faction_promotion_result", "")
    if faction_promotion_result == "success":
        # Pull pending promotion info from session state (set when trial was initiated)
        pending = (session or {}).get("pending_promotion", {})
        if pending:
            promo_faction_id = pending.get("faction_id", "")
            promo_target_rank = int(pending.get("target_rank") or 1)
            promo_player_name = pending.get("player_name", "")
            promo_template = pending.get("template", "default")
            if promo_faction_id and promo_player_name and first_char_id:
                faction_row = db.get_faction(session_id, promo_faction_id)
                if faction_row:
                    roster = faction_row.get("leadership_roster", [])
                    new_roster = promote_player_in_roster(roster, promo_player_name, promo_target_rank, promo_template)
                    db.update_faction_leadership_roster(session_id, promo_faction_id, new_roster)
                    new_title = get_rank_title(promo_template, promo_target_rank)
                    db.set_character_faction_membership(first_char_id, promo_faction_id, promo_target_rank, new_title)
            if isinstance(session, dict):
                session["pending_promotion"] = None
            db.update_session(session_id, extra={"pending_promotion": None})
    elif faction_promotion_result == "failed":
        if (session or {}).get("pending_promotion"):
            if isinstance(session, dict):
                session["pending_promotion"] = None
            db.update_session(session_id, extra={"pending_promotion": None})

def _reduce_deterministic_waypoints(session_id: int, session: dict, outcome: dict, party_uids: list, actions: list):
    """Extracted Phase 2B Reducer for Deterministic Waypoint Triggers."""
    import db, game_engine
      # ---------------------------------------------------------------- Waypoint Progression Engine
    # 1. Deterministic Arrival Triggers
    from mechanics.world.waypoints import try_advance_on_arrival, try_complete_on_skill_check
    current_location = outcome.get("location") or (session.get("current_location") if session else "") or ""
    waypoint_notices = list(outcome.get("_waypoint_notices") or [])
    pre_quest_info = (outcome.get("_pre_turn_quests") if isinstance(outcome, dict) else None) or {}
    advanced_this_turn = {
        ( k[0], k[1] )
        for k in (pre_quest_info.get("advanced_keys") or [])
        if isinstance(k, (tuple, list)) and len(k) == 2
    }  # Track (qid, so_id) to prevent pre-turn + post-turn multi-stage cascading in a single turn
  
    # We need to check all active quests & sub-objectives against current location
    active_quests = db.get_session_quests(session_id, status="Active")
    for q in active_quests:
        qid = q["quest_id"]
        # Check parent quest (e.g. Bounties) if not already advanced pre-turn
        n = try_advance_on_arrival(session_id, qid, None, current_location) if (qid, None) not in advanced_this_turn else None
        if n:
            waypoint_notices.append(n)
            advanced_this_turn.add((qid, None))
            if n.get("all_stages_complete"):
                evt = QuestCompletedEvent(session_id=session_id, quest_id=qid, party_uids=party_uids)
                bus.publish(evt)
                bounty_reward = evt.result
                if bounty_reward and bounty_reward.get("claimed"):
                    if "_quest_reward_notices" not in outcome:
                        outcome["_quest_reward_notices"] = []
                    outcome["_quest_reward_notices"].append(bounty_reward)
        elif not q.get("is_story_quest"):
            # Self-healing: if an active bounty has already completed all waypoints but was not yet claimed
            wps = db.get_quest_waypoints(session_id, qid, None)
            if wps and all(w.get("status") == "completed" for w in wps):
                evt = QuestCompletedEvent(session_id=session_id, quest_id=qid, party_uids=party_uids)
                bus.publish(evt)
                bounty_reward = evt.result
                if bounty_reward and bounty_reward.get("claimed"):
                    if "_quest_reward_notices" not in outcome:
                        outcome["_quest_reward_notices"] = []
                    outcome["_quest_reward_notices"].append(bounty_reward)
        
        # Check sub-objectives (allow any order, but max 1 completion per turn)
        if not any(k[0] == qid and k[1] is not None for k in advanced_this_turn):
            for so in q.get("sub_objectives", []):
                if isinstance(so, dict) and not so.get("completed"):
                    so_id = so.get("id")
                    if so_id is not None and (qid, so_id) not in advanced_this_turn:
                        n = try_advance_on_arrival(session_id, qid, so_id, current_location)
                        if n:
                            waypoint_notices.append(n)
                            advanced_this_turn.add((qid, so_id))
                            break
  
    # Advance rendezvous appointments to 'arrived' when player reaches rendezvous location
    try:
        from mechanics.world.waypoints import check_location_matches_waypoint
        from mechanics.system.commitments_engine import get_active_commitments, advance_rendezvous_to_arrived
        active_commits = get_active_commitments(session_id, commitment_type="rendezvous")
        for cm in active_commits:
            if cm.get("status") in ("pending", "approaching"):
                c_loc = cm.get("target_location", "")
                if c_loc and check_location_matches_waypoint(current_location, c_loc):
                    advance_rendezvous_to_arrived(session_id, cm["id"], "player")

        pending_appts = db.get_phone_appointments(session_id, status="pending")
        for appt in pending_appts:
            appt_loc = appt.get("rendezvous_location", "")
            npc_id = appt.get("npc_id", "")
            if appt_loc and npc_id and check_location_matches_waypoint(current_location, appt_loc):
                db.update_phone_appointment_status(session_id, npc_id, "arrived")
    except Exception:
        pass
  
    # 2. Deterministic Skill Check Triggers
    # COMBAT GUARD: Generic attacks against random enemies must NOT automatically
    # complete non-combat exploration / investigation / puzzle / social quest waypoints!
    is_combat = bool(outcome and (outcome.get("_combat_log") or outcome.get("_enemy_attack_notice") or game_engine.get_active_enemies(outcome)))
    has_action_fail = any(
        (hasattr(a.get("check"), "succeeded") and a["check"].succeeded is False) or
        (isinstance(a.get("check"), dict) and a["check"].get("succeeded") is False)
        for a in (actions or [])
    )
    has_action_success = any(
        (hasattr(a.get("check"), "succeeded") and a["check"].succeeded is True) or
        (isinstance(a.get("check"), dict) and a["check"].get("succeeded") is True) or
        (a.get("stat") in ("NONE", "FREE") or (a.get("requirement") or 0) <= 0)
        for a in (actions or [])
    )
    if actions:
        has_success = has_action_success and not has_action_fail
    else:
        has_success = False
        for co in outcome.get("character_outcomes", []) or []:
            if isinstance(co, dict):
                if int(co.get("hp_change") or 0) > -10 and not co.get("status_effects"):
                    has_success = True
                    break
  
    if has_success:
        check_tier = "success"
        for a in (actions or []):
            chk = a.get("check")
            if chk:
                tier_val = getattr(chk, "tier", None) or (chk.get("tier") if isinstance(chk, dict) else None)
                if tier_val:
                    check_tier = tier_val
                    break
        active_enemies = (game_engine.get_active_enemies(outcome) or game_engine.get_active_enemies(session)) if outcome else []
        has_active_hostiles = bool(active_enemies and not outcome.get("_combat_resolved"))
        turn_count = len(session.get("history", [])) if session else 0
        action_text_combined = " ".join(str(a.get("label", "")) for a in actions if isinstance(a, dict))
        # Use only immediate outcome narrative, not future ambient prompt (next_narrative)
        narr_text_combined = outcome.get("outcome_narrative") or ""
        is_quest_act = any(a.get("is_quest_action") for a in actions if isinstance(a, dict))
        quest_action_qid = next((str(a.get("quest_id", "")) for a in actions if isinstance(a, dict) and a.get("is_quest_action")), "")
        quest_action_sub_id = next((a.get("sub_obj_id") for a in actions if isinstance(a, dict) and a.get("is_quest_action")), None)
        is_movement_act = any(
            a.get("is_movement") or
            a.get("type") == "travel" or
            any(str(a.get("label", "")).strip().lower().startswith(pfx) for pfx in ("i travel to", "travel to", "i head to", "head to", "i walk to", "walk to", "i go to", "go to", "i move to", "move to", "i return to", "return to", "i leave for", "leave for", "i journey to", "journey to"))
            for a in actions if isinstance(a, dict)
        )
  
        from mechanics.world.mobility import get_session_dialogue_partners
        active_dp_names = [p.lower() for p in get_session_dialogue_partners(session)]
        in_active_dialogue = bool(active_dp_names)
  
        # Pure movement/travel turns without explicit quest binding only advance arrival waypoints,
        # never skill check / investigation / dialogue / interaction waypoints!
        if not (is_movement_act and not is_quest_act):
            for q in active_quests:
                qid = q["quest_id"]
                if (qid, None) not in advanced_this_turn:
                    active_wp = db.get_active_waypoint(session_id, qid, None)
                    if active_wp:
                        label_lower = (active_wp.get("stage_label") or "").lower()
                        target_npc = (active_wp.get("target_npc") or "").strip().lower()
                        # In active dialogue, un-tagged actions must not advance unrelated non-dialogue/environmental waypoints
                        if in_active_dialogue and not is_quest_act:
                            if not target_npc or not any(target_npc in dp or dp in target_npc for dp in active_dp_names):
                                active_wp = None
                        if active_wp:
                            is_combat_wp = any(k in label_lower for k in ("defeat", "battle", "kill", "fight", "slay", "destroy", "overcome"))
                            if not is_combat or (is_combat_wp and outcome.get("_combat_resolved")):
                                n = try_complete_on_skill_check(
                                    session_id, qid, None, current_location, True, check_tier,
                                    action_text=action_text_combined, narrative=narr_text_combined,
                                    is_quest_action=is_quest_act, action_quest_id=quest_action_qid,
                                    action_sub_obj_id=quest_action_sub_id
                                )
                                if n:
                                    waypoint_notices.append(n)
                                    advanced_this_turn.add((qid, None))
                                    if n.get("all_stages_complete"):
                                        evt = QuestCompletedEvent(session_id=session_id, quest_id=qid, party_uids=party_uids)
                                        bus.publish(evt)
                                        bounty_reward = evt.result
                                        if bounty_reward and bounty_reward.get("claimed"):
                                            if "_quest_reward_notices" not in outcome:
                                                outcome["_quest_reward_notices"] = []
                                            outcome["_quest_reward_notices"].append(bounty_reward)
                
                # Check sub-objectives (allow any order, but max 1 completion per turn)
                if not any(k[0] == qid and k[1] is not None for k in advanced_this_turn):
                    for so in q.get("sub_objectives", []):
                        if isinstance(so, dict) and not so.get("completed"):
                            so_id = so.get("id")
                            if so_id is not None and (qid, so_id) not in advanced_this_turn:
                                active_wp = db.get_active_waypoint(session_id, qid, so_id)
                                if active_wp:
                                    target_npc = (active_wp.get("target_npc") or "").strip().lower()
                                    # In active dialogue, un-tagged actions must not advance unrelated non-dialogue/environmental waypoints
                                    if in_active_dialogue and not is_quest_act:
                                        if not target_npc or not any(target_npc in dp or dp in target_npc for dp in active_dp_names):
                                            continue
                                    label_lower = (active_wp.get("stage_label") or "").lower()
                                    is_combat_wp = any(k in label_lower for k in ("defeat", "battle", "kill", "fight", "slay", "destroy", "overcome"))
                                    so_text_lower = (so.get("text") or "").lower()
                                    requires_combat_or_delve = any(kw in so_text_lower for kw in ("survive", "defeat", "slay", "kill", "recover", "retrieve", "escape", "delve", "combat", "fight", "confront", "infiltrate"))
      
                                    if has_active_hostiles and requires_combat_or_delve:
                                        continue
                                    if turn_count <= 1 and any(kw in so_text_lower for kw in ("survive", "recover the", "retrieve the", "slay the", "defeat the", "delve through")):
                                        continue
      
                                    if not is_combat or (is_combat_wp and outcome.get("_combat_resolved")):
                                        n = try_complete_on_skill_check(
                                            session_id, qid, so_id, current_location, True, check_tier,
                                            action_text=action_text_combined, narrative=narr_text_combined,
                                            sub_obj_text=so.get("text", ""),
                                            is_quest_action=is_quest_act, action_quest_id=quest_action_qid,
                                            action_sub_obj_id=quest_action_sub_id
                                        )
                                        if n:
                                            waypoint_notices.append(n)
                                            advanced_this_turn.add((qid, so_id))
                                            break
  
    if waypoint_notices:
        outcome["_waypoint_notices"] = waypoint_notices

def _reduce_physical_state_and_memories(session_id: int, session: dict, outcome: dict, party: list, scen_key: str, actions: list):
    """Extracted Phase 2B Reducer for Physical State, Commitments, and NPC Memories."""
    import db
    from mechanics.social.physical_state import (
        merge_physical_state_updates,
        handle_location_transition,
        _infer_initial_undergarments_state
    )

    def _extract_char_uid(entry, fallback_sess=None):
        if not entry:
            return None
        char = entry[0] if isinstance(entry, (tuple, list)) else entry
        if isinstance(char, dict):
            uid = char.get("user_id") or char.get("id")
            if uid:
                return uid
        if isinstance(entry, (tuple, list)) and len(entry) > 1 and isinstance(entry[1], int):
            return entry[1]
        if fallback_sess and isinstance(fallback_sess, dict):
            t_order = fallback_sess.get("turn_order")
            if t_order and isinstance(t_order, list) and t_order[0]:
                return t_order[0]
        return None

    first_char_id = 0
    if party and isinstance(party, list) and party[0]:
        first_char_id = _extract_char_uid(party[0], session) or 0
    if not first_char_id and session:
        first_char_id = (session.get("turn_order") or [0])[0]

    pre_intimate_dict = outcome.get("_pre_turn_intimacy") if isinstance(outcome, dict) and isinstance(outcome.get("_pre_turn_intimacy"), dict) else {}
    current_phys = (
        (outcome.get("_physical_state") if isinstance(outcome, dict) and isinstance(outcome.get("_physical_state"), dict) and outcome.get("_physical_state") else None)
        or (pre_intimate_dict.get("physical_state") if isinstance(pre_intimate_dict.get("physical_state"), dict) and pre_intimate_dict.get("physical_state") else None)
        or (session.get("_physical_state") if isinstance(session, dict) and isinstance(session.get("_physical_state"), dict) and session.get("_physical_state") else None)
        or db.get_session_physical_state(session_id)
    )
    cosmetic_actors = {}
    raw_actor_poses = outcome.get("actor_poses") or {}
    if isinstance(raw_actor_poses, dict):
        for a_name, pose_val in raw_actor_poses.items():
            if not a_name or not str(a_name).strip():
                continue
            if hasattr(pose_val, "model_dump"):
                pose_val = pose_val.model_dump()
            if isinstance(pose_val, dict):
                entry_pose = {}
                if pose_val.get("posture") is not None and str(pose_val.get("posture")).strip():
                    entry_pose["posture"] = str(pose_val["posture"]).strip()[:100]
                if pose_val.get("holding") is not None and str(pose_val.get("holding")).strip():
                    entry_pose["holding"] = str(pose_val["holding"]).strip()[:100]
                if entry_pose:
                    cosmetic_actors[str(a_name).strip()] = entry_pose
            elif isinstance(pose_val, str) and pose_val.strip():
                cosmetic_actors[str(a_name).strip()] = {"posture": pose_val.strip()[:100]}

    # Fallback to legacy keys if provided by test or legacy callers
    legacy_updates = (
        outcome.get("physical_updates")
        or outcome.get("scene_state_updates")
        or outcome.get("physical_state_updates")
        or {}
    )
    phys_updates = dict(legacy_updates) if isinstance(legacy_updates, dict) else {}
    if cosmetic_actors:
        existing_actors = dict(phys_updates.get("actors") or {})
        for c_k, c_v in cosmetic_actors.items():
            if c_k not in existing_actors:
                existing_actors[c_k] = c_v
            elif isinstance(existing_actors[c_k], dict):
                existing_actors[c_k].update(c_v)
        phys_updates["actors"] = existing_actors

    # 1. Location Transition: if location changed, transition the state FIRST
    # (purges old location-bound room props and resets travel postures before merging new scene state)
    old_loc = session.get("current_location", "") if session else ""
    new_loc = outcome.get("location") or old_loc
    if new_loc != old_loc:
        from mechanics.world.mobility import get_session_dialogue_partners
        retained = set(get_session_dialogue_partners(session))
        for p_npc in ((session.get("party_npcs") or []) if session else []):
            if isinstance(p_npc, dict) and p_npc.get("name"):
                retained.add(p_npc["name"])
        for npc in (outcome.get("npcs_present") or []):
            if isinstance(npc, dict) and npc.get("name"):
                retained.add(npc["name"])
            elif isinstance(npc, str) and npc.strip():
                retained.add(npc.strip())
        current_phys = handle_location_transition(current_phys, party=party, retained_names=retained)
        party_uids = [
            (char["user_id"] if isinstance(char, dict) else char[0]["user_id"])
            for char in party if char and (isinstance(char, dict) or (isinstance(char, (tuple, list)) and len(char) > 0 and isinstance(char[0], dict)))
        ]
        bus.publish(LocationChangedEvent(
            session_id=session_id,
            old_location=old_loc,
            new_location=new_loc,
            party_uids=party_uids,
            actions=actions or []
        ))

    # 2. Merge delta updates from this turn (postures, clothing, props in the new room, intimate stage)
    updated_phys = merge_physical_state_updates(current_phys, phys_updates, party=party, scen_key=scen_key)

    # 3. Handle NPC departures: remove departed characters from active scene actors
    departures = outcome.get("npc_departures") or []
    if departures and isinstance(departures, list) and isinstance(updated_phys.get("actors"), dict):
        dep_names_lower = {str(d).strip().lower() for d in departures if d}
        updated_phys["actors"] = {
            k: v for k, v in updated_phys["actors"].items()
            if k.strip().lower() not in dep_names_lower
        }

    # 4. Ensure any new NPCs present have baseline physical grounding
    present_npcs = outcome.get("npcs_present") or []
    if isinstance(present_npcs, list) and isinstance(updated_phys.get("actors"), dict):
        from mechanics.social.physical_state import _match_actor_key
        for npc in present_npcs:
            n_name = None
            if isinstance(npc, dict) and npc.get("name"):
                n_name = npc["name"]
            elif isinstance(npc, str) and npc.strip():
                n_name = npc.strip()
            if n_name:
                matched_k = _match_actor_key(n_name, updated_phys["actors"])
                if matched_k not in updated_phys["actors"]:
                    u_top, u_bot = _infer_initial_undergarments_state(
                        npc if isinstance(npc, dict) else {"name": n_name},
                        scen_key=scen_key,
                        session_id=session_id
                    )
                    updated_phys["actors"][n_name] = {
                        "posture": "Standing nearby",
                        "holding": "Empty hands",
                        "clothing": {
                            "top": "Clothed",
                            "bottom": "Clothed",
                            "under_top": u_top,
                            "under_bottom": u_bot,
                        },
                        "stance": "Neutral",
                    }

    # 5. Combat vs Intimate mutual exclusion & Vitals synchronization
    import game_engine
    active_combat_enemies = game_engine.get_active_enemies(outcome) or game_engine.get_active_enemies(session)
    is_combat = bool(outcome and (outcome.get("_combat_log") or outcome.get("_enemy_attack_notice") or active_combat_enemies))
    if is_combat:
        updated_phys["intimate_contact"] = "none"
        updated_phys["climax_state"] = {"partner_climaxed": False, "player_climaxed": False}
        if active_combat_enemies and isinstance(active_combat_enemies[0], dict) and active_combat_enemies[0].get("name"):
            updated_phys["combat_focus"] = f"Engaged with {active_combat_enemies[0]['name']}"
        elif not updated_phys.get("combat_focus") or updated_phys.get("combat_focus") == "none":
            updated_phys["combat_focus"] = "Active combat engagement"
    else:
        updated_phys["combat_focus"] = "none"

    # 6. Automatic Intimate Contact inference, Climax Primacy & Disengagement Clearance
    if not is_combat:
        from mechanics.social.physical_state import (
            is_erotic_intimate_contact,
            detect_intimate_disengagement,
            _match_actor_key,
        )
        from mechanics.world.mobility import get_session_dialogue_partners
        dps = get_session_dialogue_partners(session)
        if not dps and outcome.get("dialogue_partners"):
            dps = [p for p in outcome["dialogue_partners"] if p]
        partner = dps[0] if dps else ""
        if not partner and outcome.get("dialogue_partner"):
            partner = outcome["dialogue_partner"]
        if not partner:
            for rel in (outcome.get("relationship_updates") or []):
                if isinstance(rel, dict) and (rel.get("npc_name") or rel.get("name")):
                    partner = str(rel.get("npc_name") or rel.get("name")).strip()
                    break
        if not partner and isinstance(current_phys, dict):
            prev_ic_str = str(current_phys.get("intimate_contact") or "")
            if " with " in prev_ic_str and prev_ic_str.lower() != "none":
                raw_ic_p = prev_ic_str.split(" with ")[-1].split("(")[0].strip()
                split_ic_p = [
                    sp.strip()
                    for chunk in raw_ic_p.split(",")
                    for sp in chunk.split(" and ")
                    if sp.strip() and sp.strip().lower() != "partner"
                ]
                if split_ic_p:
                    partner = split_ic_p[0]
                    if not dps and len(split_ic_p) >= 2:
                        dps = split_ic_p
                else:
                    partner = raw_ic_p

        player_name = "Hero"
        if party and isinstance(party, list) and party[0]:
            p_char = party[0][0] if isinstance(party[0], (tuple, list)) else party[0]
            if isinstance(p_char, dict) and p_char.get("name"):
                player_name = p_char["name"]

        def _sync_char_outcome_status(char_name: str, new_effs_list: list):
            c_low_sync = str(char_name).lower().strip()
            for co_item in (outcome.get("character_outcomes") or []):
                if isinstance(co_item, dict) and str(co_item.get("name", "")).lower().strip() == c_low_sync:
                    co_item["status_effects"] = list(new_effs_list)

        def _sync_player_outcome_status(new_effs_list: list):
            _sync_char_outcome_status(player_name, new_effs_list)

        def _sync_companion_party_status(partner_name: str, new_effs_list: list):
            if not partner_name:
                return
            p_name_low = str(partner_name).lower().strip()
            p_first = (p_name_low.split() or [""])[0]
            s_dict = session or (db.get_session(session_id) if session_id else {}) or {}
            for entry in (party or [])[1:]:
                comp_c = entry[0] if isinstance(entry, (tuple, list)) else entry
                if isinstance(comp_c, dict):
                    c_name = str(comp_c.get("name", "")).lower().strip()
                    c_first = (c_name.split() or [""])[0]
                    if c_name == p_name_low or (len(p_first) >= 3 and c_first == p_first) or (p_name_low in c_name or c_name in p_name_low):
                        comp_uid = _extract_char_uid(entry, s_dict)
                        if comp_uid:
                            try:
                                db.set_status_effects(comp_uid, list(new_effs_list))
                            except Exception:
                                pass
                        comp_c["status_effects"] = list(new_effs_list)
                        _sync_char_outcome_status(comp_c.get("name", partner_name), new_effs_list)

        prev_climax_on_disengage = dict(
            (current_phys.get("climax_state") if isinstance(current_phys, dict) else None)
            or updated_phys.get("climax_state")
            or {}
        )

        is_disengagement = detect_intimate_disengagement(actions)
        act_text_raw = " ".join(((a.get("label") or "") if isinstance(a, dict) else str(a)).lower() for a in (actions or []))
        is_explicit_withdrawal = any(
            k in act_text_raw
            for k in (
                "withdraw", "pull away", "step back", "step away",
                "break contact", "break away", "leave the bed", "leave the room", "get dressed",
                "part ways", "goodbye", "farewell", "walk away", "turn away"
            )
        )
        is_aftercare_act = any(
            k in act_text_raw
            for k in (
                "aftercare", "post-climax warmth", "quiet post-climax",
                "wrapped securely in your arms", "catch your breath against",
                "promise to make it up to"
            )
        ) and not is_explicit_withdrawal
        if is_disengagement and not is_aftercare_act:
            updated_phys["intimate_contact"] = "none"
            if "excitement" in updated_phys and isinstance(updated_phys["excitement"], dict):
                had_any_climax_dis = bool(
                    prev_climax_on_disengage.get("player_climaxed")
                    or prev_climax_on_disengage.get("partner_climaxed")
                    or any((prev_climax_on_disengage.get("partner_climaxes") or {}).values())
                )
                if had_any_climax_dis and not updated_phys["excitement"].get("refractory_until_minute"):
                    from mechanics.social.intimate_excitement import calculate_refractory_duration
                    sess_dis = session or (db.get_session(session_id) if session_id else {}) or {}
                    p_end_dis = int((p_char.get("end_") or p_char.get("endurance") or 10) if isinstance(p_char, dict) else 10)
                    cd_dur_dis = calculate_refractory_duration(p_end_dis)
                    updated_phys["excitement"]["refractory_until_minute"] = (sess_dis.get("current_day", 1) * 1440) + sess_dis.get("current_minute", 480) + cd_dur_dis
                    updated_phys["excitement"]["cooldown_notified"] = False
                if updated_phys["excitement"].get("refractory_until_minute"):
                    if updated_phys["excitement"].get("player_in_refractory") is None:
                        updated_phys["excitement"]["player_in_refractory"] = bool(prev_climax_on_disengage.get("player_climaxed", False))
                    refr_p_dis = updated_phys["excitement"].setdefault("refractory_partners", {})
                    if isinstance(prev_climax_on_disengage.get("partner_climaxes"), dict) and prev_climax_on_disengage.get("partner_climaxes"):
                        for pk, pv in prev_climax_on_disengage["partner_climaxes"].items():
                            if pv:
                                refr_p_dis[pk] = True
                    elif prev_climax_on_disengage.get("partner_climaxed") and partner:
                        refr_p_dis[partner] = True
                updated_phys["excitement"]["active"] = False
                updated_phys["excitement"]["last_act"] = "none"
                updated_phys["excitement"]["premature_finish"] = False
                updated_phys["excitement"]["partner_demanded"] = False
                updated_phys["excitement"]["unsatisfied_partner"] = ""
                updated_phys["excitement"]["unsatisfied_partners"] = []
                updated_phys["excitement"]["simultaneous_partner_climax"] = False
                updated_phys["excitement"]["mutual_group_climax"] = False
            updated_phys["climax_state"] = {"partner_climaxed": False, "player_climaxed": False, "partner_climaxes": {}}

        # Dialogue partner switch clearance: if talking to a new NPC without referencing intimate partner, clear contact
        if dps:
            for dp in dps:
                db.update_contact_in_person_timestamp(session_id, dp)
        outcome_dps = outcome.get("dialogue_partners") or ([outcome["dialogue_partner"]] if outcome.get("dialogue_partner") else [])
        for odp in outcome_dps:
            if odp:
                db.update_contact_in_person_timestamp(session_id, odp)
        for rel in (outcome.get("relationship_updates", []) or []):
            if isinstance(rel, dict) and rel.get("npc_name"):
                db.update_contact_in_person_timestamp(session_id, rel["npc_name"])

        partner_switched_clear = False
        if dps and updated_phys.get("intimate_contact") not in ("none", ""):
            curr_ic = updated_phys["intimate_contact"].lower()
            if " with " in curr_ic:
                ic_target_raw = curr_ic.split(" with ")[-1].split("(")[0].strip().rstrip(")")
                ic_targets = [x.strip() for x in re.split(r",|\band\b", ic_target_raw) if x.strip()] or ([ic_target_raw] if ic_target_raw else [])
                dp_matches_ic = any(
                    dp.lower() in ic_p or ic_p in dp.lower()
                    or ((dp.lower().split() or [""])[0] == (ic_p.split() or [""])[0] and len((ic_p.split() or [""])[0]) >= 3)
                    for dp in dps
                    for ic_p in ic_targets
                )
                if ic_targets and not dp_matches_ic:
                    act_text = " ".join(((a.get("label") or "") if isinstance(a, dict) else str(a)).lower() for a in (actions or []))
                    if not any(ic_p in act_text or ((ic_p.split() or [""])[0] in act_text and len((ic_p.split() or [""])[0]) >= 3) for ic_p in ic_targets):
                        updated_phys["intimate_contact"] = "none"
                        if "excitement" in updated_phys and isinstance(updated_phys["excitement"], dict):
                            had_any_climax_sw = bool(
                                prev_climax_on_disengage.get("player_climaxed")
                                or prev_climax_on_disengage.get("partner_climaxed")
                                or any((prev_climax_on_disengage.get("partner_climaxes") or {}).values())
                            )
                            if had_any_climax_sw and not updated_phys["excitement"].get("refractory_until_minute"):
                                from mechanics.social.intimate_excitement import calculate_refractory_duration
                                sess_sw = session or (db.get_session(session_id) if session_id else {}) or {}
                                p_end_sw = int((p_char.get("end_") or p_char.get("endurance") or 10) if isinstance(p_char, dict) else 10)
                                cd_dur_sw = calculate_refractory_duration(p_end_sw)
                                updated_phys["excitement"]["refractory_until_minute"] = (sess_sw.get("current_day", 1) * 1440) + sess_sw.get("current_minute", 480) + cd_dur_sw
                                updated_phys["excitement"]["cooldown_notified"] = False
                            if updated_phys["excitement"].get("refractory_until_minute"):
                                if updated_phys["excitement"].get("player_in_refractory") is None:
                                    updated_phys["excitement"]["player_in_refractory"] = bool(prev_climax_on_disengage.get("player_climaxed", False))
                                refr_p_sw = updated_phys["excitement"].setdefault("refractory_partners", {})
                                if isinstance(prev_climax_on_disengage.get("partner_climaxes"), dict) and prev_climax_on_disengage.get("partner_climaxes"):
                                    for pk, pv in prev_climax_on_disengage["partner_climaxes"].items():
                                        if pv:
                                            refr_p_sw[pk] = True
                                elif prev_climax_on_disengage.get("partner_climaxed") and ic_targets:
                                    for ic_t in ic_targets:
                                        refr_p_sw[ic_t] = True
                            updated_phys["excitement"]["active"] = False
                            updated_phys["excitement"]["last_act"] = "none"
                            updated_phys["excitement"]["premature_finish"] = False
                            updated_phys["excitement"]["partner_demanded"] = False
                            updated_phys["excitement"]["unsatisfied_partner"] = ""
                            updated_phys["excitement"]["unsatisfied_partners"] = []
                        updated_phys["climax_state"] = {"partner_climaxed": False, "player_climaxed": False, "partner_climaxes": {}}
                        partner_switched_clear = True

        # Climax detection & Player Climax Primacy
        if not is_disengagement or is_aftercare_act:
            act_text = " ".join(((a.get("label") or "") if isinstance(a, dict) else str(a)).lower() for a in (actions or []))
            narrative_text = f"{outcome.get('outcome_narrative', '')} {outcome.get('next_narrative', '')}"
            full_turn_text = f"{act_text} {narrative_text}"

            prev_ic = "none" if partner_switched_clear else (current_phys.get("intimate_contact", "none") if isinstance(current_phys, dict) else "none")
            curr_ic = updated_phys.get("intimate_contact", "none")
            was_erotic = False if partner_switched_clear else is_erotic_intimate_contact(prev_ic)
            is_erotic = is_erotic_intimate_contact(curr_ic)

            phys_up_dict = outcome.get("physical_updates") or outcome.get("physical_state_updates") or {}
            if hasattr(phys_up_dict, "model_dump"):
                phys_up_dict = phys_up_dict.model_dump()
            elif not isinstance(phys_up_dict, dict):
                phys_up_dict = {}

            # Excitement Meter Step calculation
            from mechanics.social.intimate_excitement import (
                compute_excitement_step, check_and_resolve_refractory_clock,
                format_compact_discord_meter, classify_intimate_act,
                is_in_refractory_cooldown, format_refractory_status_tag,
                format_partner_recovery_status_tag, calculate_refractory_duration
            )

            sess_dict = session or (db.get_session(session_id) if session_id else {}) or {}

            from .core import is_check_success
            action_succeeded = True
            for a in (actions or []):
                if isinstance(a, dict):
                    if a.get("success") is False or not is_check_success(a.get("check"), default_if_none=True):
                        action_succeeded = False
                        break

            # Start from verified prior climax_state and resolve refractory clock recovery BEFORE excitement step
            prev_climax_st = ({} if partner_switched_clear else ((current_phys.get("climax_state") if isinstance(current_phys, dict) else None) or {}))
            prev_p_climaxes = prev_climax_st.get("partner_climaxes") if isinstance(prev_climax_st, dict) else None
            updated_phys["climax_state"] = {
                "partner_climaxed": bool(prev_climax_st.get("partner_climaxed", False)),
                "player_climaxed": bool(prev_climax_st.get("player_climaxed", False)),
                "partner_climaxes": dict(prev_p_climaxes) if isinstance(prev_p_climaxes, dict) else {},
            }
            is_recovered, toast_notice = check_and_resolve_refractory_clock(sess_dict, updated_phys)
            if is_recovered:
                if toast_notice:
                    outcome["_refractory_recovered_notice"] = toast_notice
                try:
                    for entry in (party or []):
                        ch_lead = entry[0] if isinstance(entry, (tuple, list)) else entry
                        u_lead = _extract_char_uid(entry, sess_dict)
                        if u_lead:
                            char_rec = db.get_character(u_lead) if u_lead else None
                            cur_effs = char_rec.get("status_effects") if char_rec else []
                            if isinstance(cur_effs, str):
                                try:
                                    cur_effs = json.loads(cur_effs)
                                except Exception:
                                    cur_effs = [cur_effs] if cur_effs else []
                            cur_effs = [s for s in cur_effs if s and s not in ("[]", "{}", '""', "''") and not any(k in str(s).lower() for k in ("refractory", "spent", "aroused", "breathless", "satisfied"))]
                            db.set_status_effects(u_lead, cur_effs)
                            if isinstance(ch_lead, dict):
                                ch_lead["status_effects"] = cur_effs
                            _sync_char_outcome_status(ch_lead.get("name", player_name) if isinstance(ch_lead, dict) else player_name, cur_effs)
                    all_c_list = db.get_contacts(session_id) or [] if session_id else []
                    for c_full in all_c_list:
                        if isinstance(c_full, dict) and c_full.get("name"):
                            c_effs = c_full.get("status_effects") or []
                            if any(k in str(s).lower() for s in c_effs for k in ("refractory", "satisfied", "spent")):
                                c_id = c_full.get("npc_id") or c_full.get("contact_id") or str(c_full.get("name")).lower().replace(" ", "_")
                                c_effs = [s for s in c_effs if s and s not in ("[]", "{}", '""', "''") and not any(k in str(s).lower() for k in ("refractory", "spent", "aroused", "breathless", "satisfied"))]
                                db.update_contact_status_effects(session_id, c_id, first_char_id, c_effs)
                                _sync_companion_party_status(c_full.get("name"), c_effs)
                except Exception as e:
                    log.debug("Could not clear refractory status on clock recovery: %s", e)
            else:
                try:
                    in_refr_tick, refr_mins_tick = is_in_refractory_cooldown(sess_dict, updated_phys)
                    if in_refr_tick and refr_mins_tick > 0:
                        exc_tick = updated_phys.get("excitement") or {}
                        pl_in_refr_tick = (
                            bool(exc_tick.get("player_in_refractory"))
                            if exc_tick.get("player_in_refractory") is not None
                            else bool((updated_phys.get("climax_state") or {}).get("player_climaxed", False))
                        )
                        refr_p_tick = exc_tick.get("refractory_partners") if isinstance(exc_tick.get("refractory_partners"), dict) else {}
                        party_list_tick = party or []
                        lead_user_id_tick = (party_list_tick[0][0]["user_id"] if isinstance(party_list_tick[0], (tuple, list)) else party_list_tick[0].get("user_id")) if party_list_tick else None
                        for entry in party_list_tick:
                            ch_lead = entry[0] if isinstance(entry, (tuple, list)) else entry
                            u_lead = _extract_char_uid(entry, sess_dict)
                            if u_lead:
                                char_rec = db.get_character(u_lead) if u_lead else None
                                cur_effs = char_rec.get("status_effects") if char_rec else []
                                if isinstance(cur_effs, str):
                                    try:
                                        cur_effs = json.loads(cur_effs)
                                    except Exception:
                                        cur_effs = [cur_effs] if cur_effs else []
                                is_lead = (u_lead == lead_user_id_tick)
                                ch_name = ch_lead.get("name", "") if isinstance(ch_lead, dict) else ""
                                m_k_t = _match_actor_key(ch_name, refr_p_tick) if refr_p_tick else ""
                                ch_in_refr = pl_in_refr_tick if is_lead else bool(refr_p_tick.get(m_k_t or ch_name, False))
                                cur_effs = [s for s in cur_effs if s and s not in ("[]", "{}", '""', "''") and not any(k in str(s).lower() for k in ("refractory", "spent", "aroused", "breathless", "satisfied"))]
                                if ch_in_refr:
                                    ch_gen_tick = (char_rec.get("gender") if char_rec else None) or (ch_lead.get("gender") if isinstance(ch_lead, dict) else ("Male" if is_lead else "Female"))
                                    refr_tag_tick = format_partner_recovery_status_tag(refr_mins_tick, ch_gen_tick)
                                    cur_effs.append(refr_tag_tick)
                                db.set_status_effects(u_lead, cur_effs)
                                if isinstance(ch_lead, dict):
                                    ch_lead["status_effects"] = cur_effs
                                _sync_char_outcome_status(ch_name or player_name, cur_effs)
                        all_c_tick = db.get_contacts(session_id) or [] if session_id else []
                        for c_full in all_c_tick:
                            if isinstance(c_full, dict) and c_full.get("name"):
                                c_effs = c_full.get("status_effects") or []
                                c_name_t = c_full.get("name", "")
                                m_k_t = _match_actor_key(c_name_t, refr_p_tick) if refr_p_tick else ""
                                if bool(refr_p_tick.get(m_k_t or c_name_t, False)) or any(k in str(s).lower() for s in c_effs for k in ("refractory", "satisfied")):
                                    c_id = c_full.get("npc_id") or c_full.get("contact_id") or str(c_name_t).lower().replace(" ", "_")
                                    p_gen_t = (c_full.get("appearance") or {}).get("gender") or c_full.get("gender") or "Female"
                                    p_rec_tag_t = format_partner_recovery_status_tag(refr_mins_tick, p_gen_t)
                                    c_effs = [s for s in c_effs if s and s not in ("[]", "{}", '""', "''") and not any(k in str(s).lower() for k in ("refractory", "spent", "aroused", "breathless", "satisfied"))]
                                    c_effs.append(p_rec_tag_t)
                                    db.update_contact_status_effects(session_id, c_id, first_char_id, c_effs)
                                    _sync_companion_party_status(c_name_t, c_effs)
                except Exception as e:
                    log.debug("Could not refresh refractory countdown on turn: %s", e)

            # Pre-infer intimate_contact from relationship_updates milestone_event if still "none"
            if updated_phys.get("intimate_contact") in ("none", "", None) and action_succeeded:
                rel_updates_list = outcome.get("relationship_updates", []) or []
                rel_milestone_npcs = [
                    str(r.get("npc_name")).strip()
                    for r in rel_updates_list
                    if isinstance(r, dict) and r.get("milestone_event") and r.get("npc_name")
                ]
                for rel in rel_updates_list:
                    if isinstance(rel, dict) and rel.get("milestone_event"):
                        m_ev = str(rel["milestone_event"]).lower().strip()
                        if len(dps) >= 2 and (
                            len(rel_milestone_npcs) >= 2
                            or sum(1 for d in dps if d.lower() in act_text or (d.lower().split() or [""])[0] in act_text) >= 2
                        ):
                            npc_target = " and ".join(dps)
                        else:
                            npc_target = rel.get("npc_name") or partner or "partner"
                        if not partner and npc_target != "partner":
                            partner = dps[0] if dps else npc_target
                        if m_ev in ("first_kiss", "kiss"):
                            updated_phys["intimate_contact"] = f"Kissing / embrace with {npc_target}"
                            break
                        elif m_ev in ("oral_give", "oral_receive", "intercourse", "manual_give", "manual_receive", "anal_give", "anal_receive", "anal"):
                            npc_to_player_act = {
                                "oral_receive": "oral give",
                                "oral_give": "oral receive",
                                "manual_receive": "manual give",
                                "manual_give": "manual receive",
                                "anal_receive": "anal give",
                                "anal_give": "anal receive",
                                "anal": "anal give",
                                "intercourse": "intercourse",
                            }
                            ic_act_label = npc_to_player_act.get(m_ev, m_ev.replace("_", " "))
                            updated_phys["intimate_contact"] = f"Intimate encounter with {npc_target} ({ic_act_label})"
                            break
                        elif m_ev in ("cuddle", "cuddling", "embrace", "embracing"):
                            updated_phys["intimate_contact"] = f"Cuddling / embrace with {npc_target}"
                            break

            curr_ic = updated_phys.get("intimate_contact", "none")
            is_erotic = is_erotic_intimate_contact(curr_ic)

            all_contacts = []
            if session_id:
                try:
                    all_contacts = db.get_contacts(session_id) or []
                except Exception:
                    all_contacts = []

            partner_contacts = []
            for dp_name in (dps or ([partner] if partner else [])):
                if not dp_name:
                    continue
                dp_low = dp_name.lower().strip()
                dp_first = (dp_low.split() or [""])[0]
                c_match = next((c for c in all_contacts if c.get("name", "").lower().strip() == dp_low), None)
                if not c_match and len(dp_first) >= 3:
                    c_match = next((c for c in all_contacts if (c.get("name", "").lower().strip().split() or [""])[0] == dp_first), None)
                if not c_match:
                    c_match = next((n for n in (sess_dict.get("current_npcs") or []) if isinstance(n, dict) and n.get("name", "").lower().strip() == dp_low), None)
                if not c_match and len(dp_first) >= 3:
                    c_match = next((n for n in (sess_dict.get("current_npcs") or []) if isinstance(n, dict) and (n.get("name", "").lower().strip().split() or [""])[0] == dp_first), None)
                if c_match:
                    if c_match.get("name", "").lower().strip() != dp_low:
                        c_match = {**c_match, "name": dp_name}
                else:
                    c_match = {"name": dp_name}
                partner_contacts.append(c_match)

            partner_contact = partner_contacts[0] if partner_contacts else None
            if not partner_contact and partner:
                partner_contact = {"name": partner}

            player_dict = p_char if isinstance(p_char, dict) else {"name": player_name}
            p_gender = str(player_dict.get("gender", "Male")).lower()
            is_female_player = "female" in p_gender or "woman" in p_gender

            target_p = partner or "partner"
            is_aftercare_transition = bool(
                is_aftercare_act
                or any(k in act_text for k in (
                    "in sweet aftercare", "in tender aftercare", "in aftercare",
                    "post-climax warmth", "quiet post-climax",
                    "wrapped securely in your arms", "catch your breath against"
                ))
                or (action_succeeded and "promise to make it up to" in act_text)
            )

            if is_aftercare_transition:
                if partner_contacts and len(partner_contacts) >= 2:
                    p_names_list = [c.get("name", "") for c in partner_contacts if c.get("name")]
                    p_names_str = " and ".join(p_names_list)
                    hold_str = f"both {p_names_str}" if len(p_names_list) == 2 else f"all of {p_names_str}"
                    updated_phys["intimate_contact"] = f"Cuddling / aftercare with {p_names_str}"
                    actors = updated_phys.get("actors", {})
                    c_matched = _match_actor_key(player_name, actors) if player_name else None
                    if c_matched and c_matched in actors:
                        actors[c_matched]["posture"] = f"Resting in aftercare, holding {hold_str}"
                    for pc_item in partner_contacts:
                        pn = pc_item.get("name", "")
                        mk = _match_actor_key(pn, actors) if pn else None
                        if mk and mk in actors:
                            actors[mk]["posture"] = f"Resting against {player_name} in shared aftercare"
                else:
                    updated_phys["intimate_contact"] = f"Cuddling / aftercare with {target_p}"
                was_premature_ac = bool((updated_phys.get("excitement") or {}).get("premature_finish"))
                unsat_partners_ac = {str(x).lower().strip() for x in ((updated_phys.get("excitement") or {}).get("unsatisfied_partners") or []) if x}
                if (updated_phys.get("excitement") or {}).get("unsatisfied_partner"):
                    unsat_partners_ac.add(str(updated_phys["excitement"]["unsatisfied_partner"]).lower().strip())
                if "excitement" in updated_phys and isinstance(updated_phys["excitement"], dict):
                    updated_phys["excitement"]["active"] = False
                    updated_phys["excitement"]["last_act"] = "none"
                    updated_phys["excitement"]["premature_finish"] = False
                    updated_phys["excitement"]["partner_demanded"] = False
                    updated_phys["excitement"]["unsatisfied_partner"] = ""
                    updated_phys["excitement"]["unsatisfied_partners"] = []
                try:
                    climax_st_ac = updated_phys.get("climax_state") or {}
                    pl_clim_ac = bool(climax_st_ac.get("player_climaxed", False))
                    pt_clim_ac = bool(climax_st_ac.get("partner_climaxed", False))
                    pt_map_ac = climax_st_ac.get("partner_climaxes") if isinstance(climax_st_ac.get("partner_climaxes"), dict) else {}
                    in_refr, refr_mins = is_in_refractory_cooldown(sess_dict, updated_phys)
                    if not in_refr and (pl_clim_ac or pt_clim_ac):
                        exc_ac = updated_phys.setdefault("excitement", {})
                        p_end_ac = int(player_dict.get("end_") or player_dict.get("endurance") or 10) if isinstance(player_dict, dict) else 10
                        cd_dur_ac = calculate_refractory_duration(p_end_ac)
                        c_day_ac = sess_dict.get("current_day", 1)
                        c_min_ac = sess_dict.get("current_minute", 480)
                        exc_ac["refractory_until_minute"] = (c_day_ac * 1440) + c_min_ac + cd_dur_ac
                        exc_ac["cooldown_notified"] = False
                        in_refr, refr_mins = True, cd_dur_ac
                    if in_refr and refr_mins > 0:
                        exc_ac = updated_phys.setdefault("excitement", {})
                        if exc_ac.get("player_in_refractory") is not None:
                            pl_did_climax_ac = bool(exc_ac.get("player_in_refractory")) or pl_clim_ac
                        else:
                            pl_did_climax_ac = pl_clim_ac or (not pt_clim_ac)
                        exc_ac["player_in_refractory"] = pl_did_climax_ac
                        p_gender = "Female" if is_female_player else "Male"
                        p_refr_tag = format_partner_recovery_status_tag(refr_mins, p_gender)
                        party_list = party or []
                        lead_entry = party_list[0] if party_list else None
                        lead_c = lead_entry[0] if isinstance(lead_entry, (tuple, list)) else lead_entry
                        u_id = _extract_char_uid(lead_entry, sess_dict)
                        if u_id:
                            char_rec = db.get_character(u_id) if u_id else None
                            cur_effs = char_rec.get("status_effects") if char_rec else []
                            if isinstance(cur_effs, str):
                                try:
                                    cur_effs = json.loads(cur_effs)
                                except Exception:
                                    cur_effs = [cur_effs] if cur_effs else []
                            cur_effs = [s for s in cur_effs if s and s not in ("[]", "{}", '""', "''") and not any(k in str(s).lower() for k in ("aroused", "breathless", "spent", "refractory", "satisfied"))]
                            if pl_did_climax_ac:
                                cur_effs.append(p_refr_tag)
                            db.set_status_effects(u_id, cur_effs)
                            if isinstance(lead_c, dict):
                                lead_c["status_effects"] = cur_effs
                            _sync_player_outcome_status(cur_effs)

                        # Partner recovery tag (e.g. Satisfied [25 min] or Refractory Recovery [25 min])
                        for pc_item in (partner_contacts or ([partner_contact] if partner_contact else [])):
                            if isinstance(pc_item, dict) and pc_item.get("name"):
                                pc_name_ac = str(pc_item.get("name")).strip()
                                pc_name_low_ac = pc_name_ac.lower()
                                if pc_name_low_ac in unsat_partners_ac or (was_premature_ac and not pt_clim_ac):
                                    p_did_climax_ac = False
                                elif pt_map_ac:
                                    m_k_ac = _match_actor_key(pc_name_ac, pt_map_ac)
                                    p_did_climax_ac = bool(pt_map_ac.get(m_k_ac or pc_name_ac, False))
                                else:
                                    p_did_climax_ac = pt_clim_ac or (not pl_clim_ac and not was_premature_ac)
                                p_gen = (pc_item.get("appearance") or {}).get("gender") or pc_item.get("gender") or "Female"
                                p_rec_tag = format_partner_recovery_status_tag(refr_mins, p_gen)
                                npc_effs = [s for s in (pc_item.get("status_effects") or []) if s and s not in ("[]", "{}", '""', "''") and not any(k in str(s).lower() for k in ("aroused", "breathless", "spent", "refractory", "satisfied"))]
                                if p_did_climax_ac:
                                    npc_effs.append(p_rec_tag)
                                    exc_ac.setdefault("refractory_partners", {})[pc_name_ac] = True
                                pc_item["status_effects"] = npc_effs
                                c_id = pc_item.get("npc_id") or pc_item.get("contact_id") or str(pc_item.get("name")).lower().replace(" ", "_")
                                db.update_contact_status_effects(session_id, c_id, first_char_id, npc_effs)
                                _sync_companion_party_status(pc_name_ac, npc_effs)
                except Exception as e:
                    log.debug("Could not apply aftercare recovery status: %s", e)
            else:
                act_class = classify_intimate_act(
                    action_str=act_text if (was_erotic or is_erotic or action_succeeded) else "",
                    intimate_contact_str=curr_ic,
                    player_name=player_name,
                    partner_name=partner,
                    partner_contact=partner_contact,
                    narrative_str=narrative_text
                )
                if partner_contacts and len(partner_contacts) >= 2 and act_class["act_type"] in ("none", "foreplay_nongenital"):
                    for extra_pc in partner_contacts[1:]:
                        extra_name = extra_pc.get("name") or ""
                        if not extra_name:
                            continue
                        extra_class = classify_intimate_act(
                            action_str=act_text if (was_erotic or is_erotic or action_succeeded) else "",
                            intimate_contact_str=curr_ic,
                            player_name=player_name,
                            partner_name=extra_name,
                            partner_contact=extra_pc,
                            narrative_str=narrative_text,
                        )
                        if extra_class["act_type"] not in ("none", "foreplay_nongenital"):
                            act_class = extra_class
                            break
                        elif act_class["act_type"] == "none" and extra_class["act_type"] != "none":
                            act_class = extra_class

                is_genital_act = (
                    act_class["act_type"] not in ("none", "foreplay_nongenital")
                    and (was_erotic or is_erotic or action_succeeded)
                )
                prev_exc_active = bool((updated_phys.get("excitement") or {}).get("active", False))
                should_run_excitement = (was_erotic or is_erotic or is_genital_act or prev_exc_active) and partner_contact

                act_label = "intercourse" if act_class["act_type"] == "penetrative" else act_class["act_type"].replace("_", " ")
                prev_ic_low = str(prev_ic).lower()
                if is_genital_act and (
                    updated_phys.get("intimate_contact") in ("none", "", None)
                    or any(k in str(updated_phys.get("intimate_contact", "")).lower() for k in ("kissing", "cuddling", "holding hands"))
                    or (
                        updated_phys.get("intimate_contact") == prev_ic
                        and act_label not in prev_ic_low
                        and "partner reached climax" not in prev_ic_low
                        and any(
                            old_act in prev_ic_low
                            for old_act in (
                                "oral give", "oral receive", "oral mutual", "mutual oral", "69",
                                "manual give", "manual receive", "anal give", "anal receive", "intercourse",
                            )
                        )
                    )
                ):
                    target_label = (" and ".join(c.get("name", "") for c in partner_contacts if c.get("name"))) if (partner_contacts and len(partner_contacts) >= 2) else (partner or "partner")
                    updated_phys["intimate_contact"] = f"Intimate encounter with {target_label} ({act_label})"

                excitement_res = (
                    (outcome.get("_pre_turn_excitement_res") if isinstance(outcome, dict) else None)
                    or pre_intimate_dict.get("excitement_res")
                    or sess_dict.get("_pre_turn_excitement_res")
                )
                if excitement_res is None and should_run_excitement:
                    excitement_res = compute_excitement_step(
                        physical_state=updated_phys,
                        action_str=act_text,
                        player_char=player_dict,
                        partner_contact=partner_contact,
                        session=sess_dict,
                        narrative_str=narrative_text,
                        partner_contacts=partner_contacts,
                    )
                if excitement_res:
                    outcome["intimate_update"] = excitement_res
                    if (
                        excitement_res
                        and excitement_res.get("act_type") not in ("", "none", "foreplay_nongenital", None)
                        and act_class["act_type"] in ("none", "foreplay_nongenital")
                        and (was_erotic or is_erotic or action_succeeded)
                    ):
                        act_class["act_type"] = excitement_res["act_type"]
                        is_genital_act = True
                        act_label = "intercourse" if act_class["act_type"] == "penetrative" else act_class["act_type"].replace("_", " ")
                        if updated_phys.get("intimate_contact") in ("none", "", None) or any(
                            k in str(updated_phys.get("intimate_contact", "")).lower() for k in ("kissing", "cuddling", "holding hands")
                        ):
                            target_label = (" and ".join(c.get("name", "") for c in partner_contacts if c.get("name"))) if (partner_contacts and len(partner_contacts) >= 2) else (partner or "partner")
                            updated_phys["intimate_contact"] = f"Intimate encounter with {target_label} ({act_label})"

                    if excitement_res and excitement_res.get("all_cooled_down"):
                        updated_phys["intimate_contact"] = "none"
                        if "excitement" in updated_phys and isinstance(updated_phys["excitement"], dict):
                            updated_phys["excitement"]["active"] = False
                            updated_phys["excitement"]["last_act"] = "none"

                    # Synchronize Aroused [3 turns] status effect on player and partner when stimulated or sensual maintenance
                    is_stimulating_turn = bool(
                        excitement_res
                        and (
                            excitement_res.get("player_stimulated")
                            or excitement_res.get("any_partner_stimulated")
                            or excitement_res.get("is_sensual_action")
                            or is_genital_act
                            or (excitement_res.get("player_delta", 0) > 0)
                            or (excitement_res.get("partner_delta", 0) > 0)
                        )
                        and not excitement_res.get("all_cooled_down")
                    )

                    if is_stimulating_turn:
                        in_refr_p, refr_mins_p = is_in_refractory_cooldown(sess_dict, updated_phys)
                        exc_curr_st = updated_phys.get("excitement") or {}
                        pl_clim_flag = (
                            bool(exc_curr_st.get("player_in_refractory"))
                            if exc_curr_st.get("player_in_refractory") is not None
                            else (bool((updated_phys.get("climax_state") or {}).get("player_climaxed", False)) or bool(excitement_res and excitement_res.get("player_climaxed")))
                        )
                        pl_gender_str = "Female" if is_female_player else "Male"
                        exc_actors_stim = (updated_phys.get("excitement") or {}).get("actors") or {}
                        p_act_k_st = _match_actor_key(player_name, exc_actors_stim) if player_name and exc_actors_stim else None
                        p_actor_st = exc_actors_stim.get(p_act_k_st or player_name) if exc_actors_stim else None
                        if isinstance(p_actor_st, dict) and "aroused_turns" in p_actor_st:
                            p_ar_t_st = int(p_actor_st.get("aroused_turns", 0) or 0)
                        else:
                            p_ar_t_st = 3
                        aroused_tag = f"Aroused [{p_ar_t_st} turn{'s' if p_ar_t_st != 1 else ''}]" if p_ar_t_st > 0 else None
                        party_list = party or []
                        lead_entry = party_list[0] if party_list else None
                        lead_c = lead_entry[0] if isinstance(lead_entry, (tuple, list)) else lead_entry
                        u_id = _extract_char_uid(lead_entry, sess_dict)
                        if u_id:
                            try:
                                char_record = db.get_character(u_id)
                                c_effs = char_record.get("status_effects") if char_record else []
                                if isinstance(c_effs, str):
                                    import json
                                    try:
                                        c_effs = json.loads(c_effs)
                                    except Exception:
                                        c_effs = [c_effs] if c_effs else []
                                else:
                                    c_effs = list(c_effs or [])
                                if in_refr_p and refr_mins_p > 0 and pl_clim_flag:
                                    refr_tag_p = format_partner_recovery_status_tag(refr_mins_p, pl_gender_str)
                                    c_effs = [s for s in c_effs if s and s not in ("[]", "{}", '""', "''") and not any(k in str(s).lower() for k in ("aroused", "breathless", "refractory", "spent", "satisfied"))]
                                    c_effs.append(refr_tag_p)
                                elif aroused_tag:
                                    if not any("aroused" in str(s).lower() for s in c_effs):
                                        c_effs.append(aroused_tag)
                                    else:
                                        c_effs = [aroused_tag if "aroused" in str(s).lower() else s for s in c_effs]
                                else:
                                    c_effs = [s for s in c_effs if "aroused" not in str(s).lower()]
                                db.set_status_effects(u_id, c_effs)
                                if isinstance(lead_c, dict):
                                    lead_c["status_effects"] = c_effs
                            except Exception as e:
                                log.debug("Could not synchronize player Aroused status: %s", e)

                        p_name_low = player_name.lower().strip()
                        for co_item in (outcome.get("character_outcomes") or []):
                            if isinstance(co_item, dict) and str(co_item.get("name", "")).lower().strip() == p_name_low:
                                co_effs = list(co_item.get("status_effects") or [])
                                if in_refr_p and refr_mins_p > 0 and pl_clim_flag:
                                    refr_tag_p = format_partner_recovery_status_tag(refr_mins_p, pl_gender_str)
                                    co_effs = [s for s in co_effs if s and s not in ("[]", "{}", '""', "''") and not any(k in str(s).lower() for k in ("aroused", "breathless", "refractory", "spent", "satisfied"))]
                                    co_effs.append(refr_tag_p)
                                elif aroused_tag:
                                    if not any("aroused" in str(s).lower() for s in co_effs):
                                        co_effs.append(aroused_tag)
                                    else:
                                        co_effs = [aroused_tag if "aroused" in str(s).lower() else s for s in co_effs]
                                else:
                                    co_effs = [s for s in co_effs if "aroused" not in str(s).lower()]
                                co_item["status_effects"] = co_effs

                        for pc_item in (partner_contacts or ([partner_contact] if partner_contact else [])):
                            if isinstance(pc_item, dict):
                                npc_effs = list(pc_item.get("status_effects") or [])
                                if any("satisfied" in str(s).lower() or "refractory" in str(s).lower() for s in npc_effs):
                                    continue
                                n_act_k_st = _match_actor_key(pc_item.get("name", ""), exc_actors_stim) if pc_item.get("name") else None
                                n_actor_st = exc_actors_stim.get(n_act_k_st or pc_item.get("name", "")) if exc_actors_stim else None
                                if isinstance(n_actor_st, dict) and "aroused_turns" in n_actor_st:
                                    n_ar_t_st = int(n_actor_st.get("aroused_turns", 0) or 0)
                                else:
                                    n_ar_t_st = 3
                                n_ar_lbl_st = f"Aroused [{n_ar_t_st} turn{'s' if n_ar_t_st != 1 else ''}]" if n_ar_t_st > 0 else None
                                if n_ar_lbl_st:
                                    if not any("aroused" in str(s).lower() for s in npc_effs):
                                        npc_effs.append(n_ar_lbl_st)
                                    else:
                                        npc_effs = [n_ar_lbl_st if "aroused" in str(s).lower() else s for s in npc_effs]
                                else:
                                    npc_effs = [s for s in npc_effs if "aroused" not in str(s).lower()]
                                pc_item["status_effects"] = npc_effs
                                if pc_item.get("name"):
                                    c_id = pc_item.get("npc_id") or pc_item.get("contact_id") or str(pc_item.get("name")).lower().replace(" ", "_")
                                    try:
                                        db.update_contact_status_effects(session_id, c_id, first_char_id, pc_item["status_effects"])
                                    except Exception:
                                        pass
                                    _sync_companion_party_status(pc_item.get("name"), pc_item["status_effects"])
                    elif excitement_res:
                        all_cooled = bool(excitement_res.get("all_cooled_down"))
                        exc_actors_map = (updated_phys.get("excitement") or {}).get("actors") or {}
                        p_act_k = _match_actor_key(player_name, exc_actors_map) if player_name else None
                        p_aroused_t = 0 if all_cooled else int((exc_actors_map.get(p_act_k or player_name) or {}).get("aroused_turns", 0) or 0)
                        p_aroused_lbl = f"Aroused [{p_aroused_t} turn{'s' if p_aroused_t != 1 else ''}]" if p_aroused_t > 0 else None

                        party_list = party or []
                        lead_entry = party_list[0] if party_list else None
                        lead_c = lead_entry[0] if isinstance(lead_entry, (tuple, list)) else lead_entry
                        u_id = _extract_char_uid(lead_entry, sess_dict)
                        if u_id:
                            try:
                                char_record = db.get_character(u_id)
                                c_effs = char_record.get("status_effects") if char_record else []
                                if isinstance(c_effs, str):
                                    import json
                                    try:
                                        c_effs = json.loads(c_effs)
                                    except Exception:
                                        c_effs = [c_effs] if c_effs else []
                                else:
                                    c_effs = list(c_effs or [])
                                if p_aroused_lbl and any("aroused" in str(s).lower() for s in c_effs):
                                    c_effs = [p_aroused_lbl if "aroused" in str(s).lower() else s for s in c_effs if s and s not in ("[]", "{}", '""', "''")]
                                else:
                                    c_effs = [s for s in c_effs if s and s not in ("[]", "{}", '""', "''") and "aroused" not in str(s).lower()]
                                db.set_status_effects(u_id, c_effs)
                                if isinstance(lead_c, dict):
                                    lead_c["status_effects"] = c_effs
                            except Exception as e:
                                log.debug("Could not update player Aroused status on non-stimulating turn: %s", e)

                        p_name_low = player_name.lower().strip()
                        for co_item in (outcome.get("character_outcomes") or []):
                            if isinstance(co_item, dict) and str(co_item.get("name", "")).lower().strip() == p_name_low:
                                co_effs = list(co_item.get("status_effects") or [])
                                if p_aroused_lbl and any("aroused" in str(s).lower() for s in co_effs):
                                    co_effs = [p_aroused_lbl if "aroused" in str(s).lower() else s for s in co_effs]
                                else:
                                    co_effs = [s for s in co_effs if "aroused" not in str(s).lower()]
                                co_item["status_effects"] = co_effs

                        for pc_item in (partner_contacts or ([partner_contact] if partner_contact else [])):
                            if isinstance(pc_item, dict):
                                cur_npc_effs = list(pc_item.get("status_effects") or [])
                                if not all_cooled and any("satisfied" in str(s).lower() or "refractory" in str(s).lower() for s in cur_npc_effs):
                                    continue
                                n_act_k = _match_actor_key(pc_item.get("name", ""), exc_actors_map) if pc_item.get("name") else None
                                n_aroused_t = 0 if all_cooled else int((exc_actors_map.get(n_act_k or pc_item.get("name", "")) or {}).get("aroused_turns", 0) or 0)
                                n_aroused_lbl = f"Aroused [{n_aroused_t} turn{'s' if n_aroused_t != 1 else ''}]" if n_aroused_t > 0 else None
                                if n_aroused_lbl and any("aroused" in str(s).lower() for s in cur_npc_effs):
                                    pc_item["status_effects"] = [n_aroused_lbl if "aroused" in str(s).lower() else s for s in cur_npc_effs]
                                else:
                                    pc_item["status_effects"] = [s for s in cur_npc_effs if "aroused" not in str(s).lower()]
                                if pc_item.get("name"):
                                    c_id = pc_item.get("npc_id") or pc_item.get("contact_id") or str(pc_item.get("name")).lower().replace(" ", "_")
                                    try:
                                        db.update_contact_status_effects(session_id, c_id, first_char_id, pc_item["status_effects"])
                                    except Exception:
                                        pass
                                    _sync_companion_party_status(pc_item.get("name"), pc_item["status_effects"])
                else:
                    # Tick down lingering Aroused [N turns] when excitement engine is inactive
                    party_list = party or []
                    lead_entry = party_list[0] if party_list else None
                    lead_c = lead_entry[0] if isinstance(lead_entry, (tuple, list)) else lead_entry
                    u_id = _extract_char_uid(lead_entry, sess_dict)
                    if u_id:
                        try:
                            char_record = db.get_character(u_id)
                            c_effs = char_record.get("status_effects") if char_record else []
                            if isinstance(c_effs, str):
                                import json
                                try:
                                    c_effs = json.loads(c_effs)
                                except Exception:
                                    c_effs = [c_effs] if c_effs else []
                            else:
                                c_effs = list(c_effs or [])
                            if any("aroused" in str(s).lower() for s in c_effs):
                                new_c_effs = []
                                next_aroused_t = 0
                                for s in c_effs:
                                    if not s or s in ("[]", "{}", '""', "''"):
                                        continue
                                    if "aroused" in str(s).lower():
                                        m_ar = re.search(r"\[(\d+)\s*turns?\]", str(s), re.IGNORECASE)
                                        cur_t = int(m_ar.group(1)) if m_ar else 1
                                        next_aroused_t = max(0, cur_t - 1)
                                        if next_aroused_t > 0:
                                            new_c_effs.append(f"Aroused [{next_aroused_t} turn{'s' if next_aroused_t != 1 else ''}]")
                                    else:
                                        new_c_effs.append(s)
                                db.set_status_effects(u_id, new_c_effs)
                                if isinstance(lead_c, dict):
                                    lead_c["status_effects"] = new_c_effs
                                _sync_player_outcome_status(new_c_effs)
                                exc_actors_map = (updated_phys.get("excitement") or {}).get("actors") or {}
                                p_act_k = _match_actor_key(player_name, exc_actors_map) if player_name else None
                                if p_act_k and isinstance(exc_actors_map.get(p_act_k), dict):
                                    exc_actors_map[p_act_k]["aroused_turns"] = next_aroused_t
                        except Exception as e:
                            log.debug("Could not tick down inactive Aroused status: %s", e)
                    if session_id:
                        try:
                            exc_actors_map = (updated_phys.get("excitement") or {}).get("actors") or {}
                            for c_full in (db.get_contacts(session_id) or []):
                                if isinstance(c_full, dict) and c_full.get("name"):
                                    c_effs = list(c_full.get("status_effects") or [])
                                    if any("aroused" in str(s).lower() for s in c_effs):
                                        new_npc_effs = []
                                        next_npc_t = 0
                                        for s in c_effs:
                                            if not s or s in ("[]", "{}", '""', "''"):
                                                continue
                                            if "aroused" in str(s).lower():
                                                m_ar = re.search(r"\[(\d+)\s*turns?\]", str(s), re.IGNORECASE)
                                                cur_t = int(m_ar.group(1)) if m_ar else 1
                                                next_npc_t = max(0, cur_t - 1)
                                                if next_npc_t > 0:
                                                    new_npc_effs.append(f"Aroused [{next_npc_t} turn{'s' if next_npc_t != 1 else ''}]")
                                            else:
                                                new_npc_effs.append(s)
                                        c_id = c_full.get("npc_id") or c_full.get("contact_id") or str(c_full.get("name")).lower().replace(" ", "_")
                                        db.update_contact_status_effects(session_id, c_id, first_char_id, new_npc_effs)
                                        _sync_companion_party_status(c_full.get("name"), new_npc_effs)
                                        n_act_k = _match_actor_key(c_full.get("name", ""), exc_actors_map)
                                        if n_act_k and isinstance(exc_actors_map.get(n_act_k), dict):
                                            exc_actors_map[n_act_k]["aroused_turns"] = next_npc_t
                        except Exception as e:
                            log.debug("Could not tick down inactive NPC Aroused status: %s", e)

                if excitement_res:
                    has_player_climax = bool(excitement_res.get("player_climaxed"))
                    has_partner_climax = bool(excitement_res.get("partner_climaxed"))
                else:
                    has_player_climax = bool(phys_up_dict.get("player_climaxed") is True)
                    has_partner_climax = bool(phys_up_dict.get("partner_climaxed") is True)

                partner_climaxes_res = (excitement_res.get("partner_climaxes") if excitement_res else None) or {}
                all_partners_climaxed = (
                    bool(partner_climaxes_res and all(bool(v) for v in partner_climaxes_res.values()))
                    if partner_climaxes_res
                    else bool(has_partner_climax)
                )

                target_label = (" and ".join(c.get("name", "") for c in partner_contacts if c.get("name"))) if (partner_contacts and len(partner_contacts) >= 2) else target_p
                _eff_act_type = act_class["act_type"]
                if _eff_act_type in ("", "none", "foreplay_nongenital"):
                    _exc_last = str((updated_phys.get("excitement") or {}).get("last_act") or "").strip().lower()
                    if _exc_last not in ("", "none", "foreplay_nongenital"):
                        _eff_act_type = _exc_last
                _ongoing_act_label = (
                    _eff_act_type.replace("_", " ")
                    if _eff_act_type in (
                        "oral_give", "oral_receive", "oral_mutual",
                        "manual_give", "manual_receive",
                        "anal_give", "anal_receive",
                    )
                    else "intercourse"
                )

                if has_player_climax:
                    if is_female_player and not all_partners_climaxed:
                        # Female multi-climax while at least one partner is still ongoing: drops to 35% hypersensitive baseline; ongoing rhythm
                        updated_phys["intimate_contact"] = f"Intimate encounter with {target_label} ({_ongoing_act_label} - player reached climax, hypersensitive ongoing)"
                        updated_phys["climax_state"] = {"partner_climaxed": bool(has_partner_climax), "player_climaxed": True}
                        if excitement_res and excitement_res.get("partner_climaxes"):
                            updated_phys["climax_state"]["partner_climaxes"] = dict(excitement_res["partner_climaxes"])
                        if excitement_res:
                            outcome["intimate_update"]["female_multiorgasmic"] = True
                    elif (not is_female_player) and excitement_res and excitement_res.get("premature_finish"):
                        # Male anatomy climax: physical penetration ceases, partner unsatisfied (< 100%)
                        updated_phys["intimate_contact"] = f"Intimate encounter with {target_label} (player reached climax spent, partner unsatisfied)"
                        updated_phys["climax_state"] = {"partner_climaxed": bool(has_partner_climax), "player_climaxed": True}
                        if excitement_res and excitement_res.get("partner_climaxes"):
                            updated_phys["climax_state"]["partner_climaxes"] = dict(excitement_res["partner_climaxes"])
                        try:
                            in_refr, refr_mins = is_in_refractory_cooldown(sess_dict, updated_phys)
                            if not in_refr:
                                exc_pf = updated_phys.setdefault("excitement", {})
                                p_end_pf = int(player_dict.get("end_") or player_dict.get("endurance") or 10) if isinstance(player_dict, dict) else 10
                                cd_dur_pf = calculate_refractory_duration(p_end_pf)
                                exc_pf["refractory_until_minute"] = (sess_dict.get("current_day", 1) * 1440) + sess_dict.get("current_minute", 480) + cd_dur_pf
                                exc_pf["cooldown_notified"] = False
                                in_refr, refr_mins = True, cd_dur_pf
                            if in_refr and refr_mins > 0:
                                updated_phys.setdefault("excitement", {})["player_in_refractory"] = True
                                p_refr_tag = format_refractory_status_tag(refr_mins)
                                party_list = party or []
                                lead_entry = party_list[0] if party_list else None
                                lead_c = lead_entry[0] if isinstance(lead_entry, (tuple, list)) else lead_entry
                                u_id = _extract_char_uid(lead_entry, sess_dict)
                                if u_id:
                                    char_rec = db.get_character(u_id) if u_id else None
                                    cur_effs = char_rec.get("status_effects") if char_rec else []
                                    if isinstance(cur_effs, str):
                                        try:
                                            cur_effs = json.loads(cur_effs)
                                        except Exception:
                                            cur_effs = [cur_effs] if cur_effs else []
                                    cur_effs = [s for s in cur_effs if s and s not in ("[]", "{}", '""', "''") and not any(k in str(s).lower() for k in ("aroused", "breathless", "spent", "refractory"))]
                                    cur_effs.append(p_refr_tag)
                                    db.set_status_effects(u_id, cur_effs)
                                    if isinstance(lead_c, dict):
                                        lead_c["status_effects"] = cur_effs
                                    _sync_player_outcome_status(cur_effs)
                        except Exception as e:
                            log.debug("Could not apply premature finish refractory tag: %s", e)
                        if has_partner_climax:
                            actors = updated_phys.get("actors", {})
                            partner_climaxes_map = excitement_res.get("partner_climaxes") or {}
                            in_refr_pf, refr_mins_pf = is_in_refractory_cooldown(sess_dict, updated_phys)
                            for pc_item in (partner_contacts or ([{"name": target_p}] if target_p else [])):
                                p_name_item = pc_item.get("name", "")
                                if not p_name_item:
                                    continue
                                m_key = _match_actor_key(p_name_item, actors)
                                p_clim_k = _match_actor_key(p_name_item, partner_climaxes_map) if partner_climaxes_map else ""
                                p_clim = bool(partner_climaxes_map.get(p_clim_k or p_name_item, False)) if partner_climaxes_map else has_partner_climax
                                if m_key in actors:
                                    posture_str = str(actors[m_key].get("posture", "")).lower()
                                    other_names = [c.get("name", "") for c in partner_contacts if c.get("name") and c.get("name") != p_name_item]
                                    other_names_str = " and ".join(other_names)
                                    if p_clim and any(k in posture_str for k in ("sleeping", "asleep", "lying down spent", "resting side by side", "resting close beside", "post-coital", "standing", "")):
                                        if other_names:
                                            actors[m_key]["posture"] = f"Trembling from aftershocks beside {player_name} and {other_names_str}"
                                        else:
                                            actors[m_key]["posture"] = f"Trembling from aftershocks in {player_name}'s embrace"
                                if p_clim and in_refr_pf and refr_mins_pf > 0 and isinstance(pc_item, dict):
                                    p_gen_pf = (pc_item.get("appearance") or {}).get("gender") or pc_item.get("gender") or "Female"
                                    p_rec_tag_pf = format_partner_recovery_status_tag(refr_mins_pf, p_gen_pf)
                                    npc_effs_pf = [s for s in (pc_item.get("status_effects") or []) if s and s not in ("[]", "{}", '""', "''") and not any(k in str(s).lower() for k in ("aroused", "breathless", "spent", "refractory", "satisfied"))]
                                    npc_effs_pf.append(p_rec_tag_pf)
                                    pc_item["status_effects"] = npc_effs_pf
                                    updated_phys.setdefault("excitement", {}).setdefault("refractory_partners", {})[p_name_item] = True
                                    c_id_pf = pc_item.get("npc_id") or pc_item.get("contact_id") or str(p_name_item).lower().replace(" ", "_")
                                    try:
                                        db.update_contact_status_effects(session_id, c_id_pf, first_char_id, npc_effs_pf)
                                    except Exception:
                                        pass
                                    _sync_companion_party_status(p_name_item, npc_effs_pf)
                    else:
                        # Mutual climax or partner was already satisfied -> aftercare
                        if partner_contacts and len(partner_contacts) >= 2:
                            p_names_list = [c.get("name", "") for c in partner_contacts if c.get("name")]
                            p_names_str = " and ".join(p_names_list)
                            hold_str = f"both {p_names_str}" if len(p_names_list) == 2 else f"all of {p_names_str}"
                            updated_phys["intimate_contact"] = f"Cuddling / aftercare with {p_names_str}"
                            actors = updated_phys.get("actors", {})
                            c_matched = _match_actor_key(player_name, actors) if player_name else None
                            if c_matched and c_matched in actors:
                                actors[c_matched]["posture"] = f"Resting in aftercare, holding {hold_str}"
                            for pc_item in partner_contacts:
                                pn = pc_item.get("name", "")
                                mk = _match_actor_key(pn, actors) if pn else None
                                if mk and mk in actors:
                                    actors[mk]["posture"] = f"Resting against {player_name} in shared aftercare"
                        else:
                            updated_phys["intimate_contact"] = f"Cuddling / aftercare with {target_p}"
                        updated_phys["climax_state"] = {"partner_climaxed": True, "player_climaxed": True}
                        if excitement_res and excitement_res.get("partner_climaxes"):
                            updated_phys["climax_state"]["partner_climaxes"] = dict(excitement_res["partner_climaxes"])
                        if "excitement" in updated_phys:
                            updated_phys["excitement"]["active"] = False
                            updated_phys["excitement"]["last_act"] = "none"
                            updated_phys["excitement"]["premature_finish"] = False
                            updated_phys["excitement"]["partner_demanded"] = False
                            updated_phys["excitement"]["unsatisfied_partner"] = ""
                            updated_phys["excitement"]["unsatisfied_partners"] = []
                        try:
                            in_refr, refr_mins = is_in_refractory_cooldown(sess_dict, updated_phys)
                            if not in_refr:
                                exc_mc = updated_phys.setdefault("excitement", {})
                                p_end_mc = int(player_dict.get("end_") or player_dict.get("endurance") or 10) if isinstance(player_dict, dict) else 10
                                cd_dur_mc = calculate_refractory_duration(p_end_mc)
                                exc_mc["refractory_until_minute"] = (sess_dict.get("current_day", 1) * 1440) + sess_dict.get("current_minute", 480) + cd_dur_mc
                                exc_mc["cooldown_notified"] = False
                                in_refr, refr_mins = True, cd_dur_mc
                            if in_refr and refr_mins > 0:
                                exc_mc = updated_phys.setdefault("excitement", {})
                                exc_mc["player_in_refractory"] = True
                                p_gender = "Female" if is_female_player else "Male"
                                p_refr_tag = format_partner_recovery_status_tag(refr_mins, p_gender)
                                party_list = party or []
                                lead_entry = party_list[0] if party_list else None
                                lead_c = lead_entry[0] if isinstance(lead_entry, (tuple, list)) else lead_entry
                                u_id = _extract_char_uid(lead_entry, sess_dict)
                                if u_id:
                                    char_rec = db.get_character(u_id) if u_id else None
                                    cur_effs = char_rec.get("status_effects") if char_rec else []
                                    if isinstance(cur_effs, str):
                                        try:
                                            cur_effs = json.loads(cur_effs)
                                        except Exception:
                                            cur_effs = [cur_effs] if cur_effs else []
                                    cur_effs = [s for s in cur_effs if s and s not in ("[]", "{}", '""', "''") and not any(k in str(s).lower() for k in ("aroused", "breathless", "spent", "refractory", "satisfied"))]
                                    cur_effs.append(p_refr_tag)
                                    db.set_status_effects(u_id, cur_effs)
                                    if isinstance(lead_c, dict):
                                        lead_c["status_effects"] = cur_effs
                                    _sync_player_outcome_status(cur_effs)

                                # Partner recovery tag (e.g. Satisfied [28 min])
                                for pc_item in (partner_contacts or ([partner_contact] if partner_contact else [])):
                                    if isinstance(pc_item, dict) and pc_item.get("name"):
                                        pc_name_mc = str(pc_item.get("name")).strip()
                                        m_k_mc = _match_actor_key(pc_name_mc, partner_climaxes_res) if partner_climaxes_res else ""
                                        p_did_clim_mc = bool(partner_climaxes_res.get(m_k_mc or pc_name_mc, True)) if partner_climaxes_res else True
                                        p_gen = (pc_item.get("appearance") or {}).get("gender") or pc_item.get("gender") or "Female"
                                        p_rec_tag = format_partner_recovery_status_tag(refr_mins, p_gen)
                                        npc_effs = [s for s in (pc_item.get("status_effects") or []) if s and s not in ("[]", "{}", '""', "''") and not any(k in str(s).lower() for k in ("aroused", "breathless", "spent", "refractory", "satisfied"))]
                                        if p_did_clim_mc:
                                            npc_effs.append(p_rec_tag)
                                            exc_mc.setdefault("refractory_partners", {})[pc_name_mc] = True
                                        pc_item["status_effects"] = npc_effs
                                        c_id = pc_item.get("npc_id") or pc_item.get("contact_id") or str(pc_item.get("name")).lower().replace(" ", "_")
                                        db.update_contact_status_effects(session_id, c_id, first_char_id, npc_effs)
                                        _sync_companion_party_status(pc_name_mc, npc_effs)
                        except Exception as e:
                            log.debug("Could not apply mutual climax recovery status: %s", e)
                elif (was_erotic or is_erotic or is_genital_act) and has_partner_climax and not has_player_climax:
                    # Partner reached climax, but player is still going! (Player Climax Primacy)
                    primacy_act = _ongoing_act_label
                    updated_phys["intimate_contact"] = f"Intimate encounter with {target_label} ({primacy_act} - partner reached climax, ongoing for player)"
                    updated_phys["climax_state"] = {"partner_climaxed": True, "player_climaxed": False}
                    if excitement_res and excitement_res.get("partner_climaxes"):
                        updated_phys["climax_state"]["partner_climaxes"] = dict(excitement_res["partner_climaxes"])
                    actors = updated_phys.get("actors", {})
                    c_matched = _match_actor_key(player_name, actors) if player_name else None
                    partner_climaxes_map = (excitement_res.get("partner_climaxes") if excitement_res else None) or {}

                    for pc_item in (partner_contacts or ([{"name": target_p}] if target_p else [])):
                        p_name_item = pc_item.get("name", "")
                        if not p_name_item:
                            continue
                        m_key = _match_actor_key(p_name_item, actors)
                        p_clim_k = _match_actor_key(p_name_item, partner_climaxes_map) if partner_climaxes_map else ""
                        p_clim = bool(partner_climaxes_map.get(p_clim_k or p_name_item, False)) if partner_climaxes_map else has_partner_climax
                        if m_key in actors:
                            posture_str = str(actors[m_key].get("posture", "")).lower()
                            other_names = [c.get("name", "") for c in partner_contacts if c.get("name") and c.get("name") != p_name_item]
                            other_names_str = " and ".join(other_names)
                            if p_clim:
                                if any(k in posture_str for k in ("sleeping", "asleep", "lying down spent", "resting side by side", "resting close beside", "post-coital", "standing", "")):
                                    if other_names:
                                        actors[m_key]["posture"] = f"Trembling from aftershocks beside {player_name} and {other_names_str}"
                                    else:
                                        actors[m_key]["posture"] = f"Trembling from aftershocks in {player_name}'s embrace"
                            elif has_partner_climax or has_player_climax:
                                if any(k in posture_str for k in ("sleeping", "asleep", "standing", "")):
                                    actors[m_key]["posture"] = f"Resting close beside {player_name} with flushed warmth"
                        if p_clim and isinstance(pc_item, dict) and ("status_effects" in pc_item or pc_item.get("contact_id") or pc_item.get("npc_id")):
                            p_gen = (pc_item.get("appearance") or {}).get("gender") or pc_item.get("gender") or "Female"
                            if str(p_gen).strip().lower() in ("male", "m"):
                                try:
                                    from mechanics.social.intimate_excitement import is_in_refractory_cooldown, format_partner_recovery_status_tag
                                    sess_for_clock = session or (db.get_session(session_id) if session_id else {}) or {}
                                    in_refr_p, refr_mins_p = is_in_refractory_cooldown(sess_for_clock, updated_phys)
                                    if not in_refr_p:
                                        exc_mp = updated_phys.setdefault("excitement", {})
                                        p_end_mp = (pc_item.get("stats") or {}).get("endurance") or pc_item.get("endurance") or 10
                                        cd_dur_mp = calculate_refractory_duration(int(p_end_mp))
                                        exc_mp["refractory_until_minute"] = (sess_for_clock.get("current_day", 1) * 1440) + sess_for_clock.get("current_minute", 480) + cd_dur_mp
                                        exc_mp["cooldown_notified"] = False
                                        in_refr_p, refr_mins_p = True, cd_dur_mp
                                    if in_refr_p and refr_mins_p > 0:
                                        exc_mp = updated_phys.setdefault("excitement", {})
                                        exc_mp.setdefault("player_in_refractory", False)
                                        exc_mp.setdefault("refractory_partners", {})[p_name_item] = True
                                        p_rec_tag = format_partner_recovery_status_tag(refr_mins_p, p_gen)
                                        npc_effs = [s for s in (pc_item.get("status_effects") or []) if s and s not in ("[]", "{}", '""', "''") and not any(k in str(s).lower() for k in ("aroused", "breathless", "spent", "refractory", "satisfied"))]
                                        npc_effs.append(p_rec_tag)
                                        pc_item["status_effects"] = npc_effs
                                        c_id = pc_item.get("npc_id") or pc_item.get("contact_id") or str(p_name_item).lower().replace(" ", "_")
                                        db.update_contact_status_effects(session_id, c_id, first_char_id, npc_effs)
                                        _sync_companion_party_status(p_name_item, npc_effs)
                                except Exception as e:
                                    log.debug("Could not apply unilateral male partner refractory status: %s", e)
                    if c_matched and c_matched in actors:
                        c_posture_str = str(actors[c_matched].get("posture", "")).lower()
                        if any(k in c_posture_str for k in ("sleeping", "asleep", "lying down spent", "resting side by side")):
                            act_t = act_class.get("act_type", "")
                            if act_t == "oral_give":
                                actors[c_matched]["posture"] = f"Kneeling between {target_p}'s thighs, maintaining oral rhythm"
                            elif act_t == "oral_receive":
                                actors[c_matched]["posture"] = f"Leaning back, receiving oral pleasure from {target_p}"
                            elif act_t == "oral_mutual":
                                actors[c_matched]["posture"] = f"Engaged intimately with {target_p} in mutual oral rhythm"
                            elif act_t == "manual_give":
                                actors[c_matched]["posture"] = f"Maintaining manual rhythm with {target_p}"
                            elif act_t == "manual_receive":
                                actors[c_matched]["posture"] = f"Resting close, receiving manual pleasure from {target_p}"
                            elif is_female_player and act_t in ("penetrative", "anal_give", "anal_receive"):
                                actors[c_matched]["posture"] = f"Maintaining rhythm with {target_p}"
                            else:
                                actors[c_matched]["posture"] = f"Maintaining rhythm inside {target_p}"
                elif was_erotic and not has_player_climax:
                    # Ongoing intercourse where neither climaxed this turn
                    if updated_phys.get("intimate_contact") in ("none", "", None) or any(k in str(updated_phys.get("intimate_contact", "")).lower() for k in ("cuddle", "cuddling", "sleeping", "aftercare", "lying down")):
                        updated_phys["intimate_contact"] = prev_ic
                        if isinstance(current_phys, dict) and current_phys.get("climax_state"):
                            updated_phys["climax_state"] = dict(current_phys["climax_state"])

            # Fallback: check actions for non-genital physical contact with dialogue partner
            if updated_phys.get("intimate_contact") == "none" and partner and action_succeeded:
                for a in (actions or []):
                    a_label = ((a.get("label") or "") if isinstance(a, dict) else str(a)).lower()
                    fb_target = (
                        " and ".join(dps)
                        if (len(dps) >= 2 and (
                            "both" in a_label
                            or sum(1 for d in dps if d.lower() in a_label or (d.lower().split() or [""])[0] in a_label) >= 2
                        ))
                        else partner
                    )
                    if any(k in a_label for k in ("kiss", "kissing", "peck on")):
                        updated_phys["intimate_contact"] = f"Kissing with {fb_target}"
                        break
                    elif any(k in a_label for k in ("hold hands", "holding hands", "take her hand", "take his hand", "clasps hands", "holding her hand", "holding his hand")):
                        updated_phys["intimate_contact"] = f"Holding hands with {fb_target}"
                        break
                    elif any(k in a_label for k in ("cuddle", "cuddling", "embrace", "embracing", "hold close", "holding close")):
                        updated_phys["intimate_contact"] = f"Cuddling / embrace with {fb_target}"
                        break
        else:
            # Check in-game clock refractory recovery even on disengagement turns
            from mechanics.social.intimate_excitement import (
                check_and_resolve_refractory_clock,
                is_in_refractory_cooldown,
                format_refractory_status_tag,
                format_partner_recovery_status_tag,
            )
            sess_for_clock = session or (db.get_session(session_id) if session_id else {}) or {}
            is_recovered, toast_notice = check_and_resolve_refractory_clock(sess_for_clock, updated_phys)
            if is_recovered:
                if toast_notice:
                    outcome["_refractory_recovered_notice"] = toast_notice
                try:
                    for entry in (party or []):
                        ch_lead = entry[0] if isinstance(entry, (tuple, list)) else entry
                        u_lead = _extract_char_uid(entry, sess_for_clock)
                        if u_lead:
                            char_rec = db.get_character(u_lead) if u_lead else None
                            cur_effs = char_rec.get("status_effects") if char_rec else []
                            if isinstance(cur_effs, str):
                                try:
                                    cur_effs = json.loads(cur_effs)
                                except Exception:
                                    cur_effs = [cur_effs] if cur_effs else []
                            cur_effs = [s for s in cur_effs if s and s not in ("[]", "{}", '""', "''") and not any(k in str(s).lower() for k in ("refractory", "spent", "aroused", "breathless", "satisfied"))]
                            db.set_status_effects(u_lead, cur_effs)
                            if isinstance(ch_lead, dict):
                                ch_lead["status_effects"] = cur_effs
                            _sync_char_outcome_status(ch_lead.get("name", player_name) if isinstance(ch_lead, dict) else player_name, cur_effs)
                    all_c_list = db.get_contacts(session_id) or [] if session_id else []
                    for c_full in all_c_list:
                        if isinstance(c_full, dict) and c_full.get("name"):
                            c_effs = c_full.get("status_effects") or []
                            if any(k in str(s).lower() for s in c_effs for k in ("refractory", "satisfied", "spent", "aroused", "breathless")):
                                c_id = c_full.get("npc_id") or c_full.get("contact_id") or str(c_full.get("name")).lower().replace(" ", "_")
                                c_effs = [s for s in c_effs if s and s not in ("[]", "{}", '""', "''") and not any(k in str(s).lower() for k in ("refractory", "spent", "aroused", "breathless", "satisfied"))]
                                db.update_contact_status_effects(session_id, c_id, first_char_id, c_effs)
                                _sync_companion_party_status(c_full.get("name"), c_effs)
                except Exception as e:
                    log.debug("Could not clear refractory status on disengagement recovery: %s", e)
            else:
                try:
                    in_refr_dis, refr_mins_dis = is_in_refractory_cooldown(sess_for_clock, updated_phys)
                    if in_refr_dis and refr_mins_dis > 0:
                        exc_dis = updated_phys.get("excitement") or {}
                        if exc_dis.get("player_in_refractory") is not None:
                            pl_climaxed_dis = bool(exc_dis.get("player_in_refractory"))
                        else:
                            pl_climaxed_dis = bool(prev_climax_on_disengage.get("player_climaxed") or (updated_phys.get("climax_state") or {}).get("player_climaxed"))
                        p_clim_map_dis = {
                            **(prev_climax_on_disengage.get("partner_climaxes") or {}),
                            **(exc_dis.get("refractory_partners") or {}),
                        }
                        lead_user_id = (party[0][0]["user_id"] if isinstance(party[0], (tuple, list)) else party[0].get("user_id")) if party else None
                        for entry in (party or []):
                            ch_lead = entry[0] if isinstance(entry, (tuple, list)) else entry
                            u_lead = _extract_char_uid(entry, sess_for_clock)
                            if u_lead:
                                char_rec = db.get_character(u_lead) if u_lead else None
                                cur_effs = char_rec.get("status_effects") if char_rec else []
                                if isinstance(cur_effs, str):
                                    try:
                                        cur_effs = json.loads(cur_effs)
                                    except Exception:
                                        cur_effs = [cur_effs] if cur_effs else []
                                cur_effs = [s for s in cur_effs if s and s not in ("[]", "{}", '""', "''") and not any(k in str(s).lower() for k in ("refractory", "spent", "aroused", "breathless", "satisfied"))]
                                is_lead_entry = (u_lead == lead_user_id)
                                ch_name = ch_lead.get("name", "") if isinstance(ch_lead, dict) else ""
                                m_k_ch = _match_actor_key(ch_name, p_clim_map_dis) if p_clim_map_dis else ""
                                ch_clim_dis = pl_climaxed_dis if is_lead_entry else bool(p_clim_map_dis.get(m_k_ch or ch_name, False))
                                if ch_clim_dis:
                                    ch_gen = (char_rec.get("gender") if char_rec else None) or (ch_lead.get("gender") if isinstance(ch_lead, dict) else "Male")
                                    refr_tag_dis = format_partner_recovery_status_tag(refr_mins_dis, ch_gen)
                                    cur_effs.append(refr_tag_dis)
                                db.set_status_effects(u_lead, cur_effs)
                                if isinstance(ch_lead, dict):
                                    ch_lead["status_effects"] = cur_effs
                                _sync_char_outcome_status(ch_name, cur_effs)
                        all_c_list = db.get_contacts(session_id) or [] if session_id else []
                        for c_full in all_c_list:
                            if isinstance(c_full, dict) and c_full.get("name"):
                                c_effs = c_full.get("status_effects") or []
                                c_name_dis = c_full.get("name", "")
                                m_k_dis = _match_actor_key(c_name_dis, p_clim_map_dis) if p_clim_map_dis else ""
                                c_climaxed_dis = bool(p_clim_map_dis.get(m_k_dis or c_name_dis, False))
                                if c_climaxed_dis or any(k in str(s).lower() for s in c_effs for k in ("refractory", "satisfied", "spent")):
                                    c_id = c_full.get("npc_id") or c_full.get("contact_id") or str(c_full.get("name")).lower().replace(" ", "_")
                                    p_gen = (c_full.get("appearance") or {}).get("gender") or c_full.get("gender") or "Female"
                                    p_rec_tag = format_partner_recovery_status_tag(refr_mins_dis, p_gen)
                                    c_effs = [s for s in c_effs if s and s not in ("[]", "{}", '""', "''") and not any(k in str(s).lower() for k in ("refractory", "spent", "aroused", "breathless", "satisfied"))]
                                    c_effs.append(p_rec_tag)
                                    db.update_contact_status_effects(session_id, c_id, first_char_id, c_effs)
                                elif any(k in str(s).lower() for s in c_effs for k in ("aroused", "breathless")):
                                    c_id = c_full.get("npc_id") or c_full.get("contact_id") or str(c_full.get("name")).lower().replace(" ", "_")
                                    c_effs = [s for s in c_effs if s and s not in ("[]", "{}", '""', "''") and not any(k in str(s).lower() for k in ("aroused", "breathless"))]
                                    db.update_contact_status_effects(session_id, c_id, first_char_id, c_effs)
                    else:
                        for entry in (party or []):
                            ch_lead = entry[0] if isinstance(entry, (tuple, list)) else entry
                            u_lead = _extract_char_uid(entry, sess_for_clock)
                            if u_lead:
                                char_rec = db.get_character(u_lead) if u_lead else None
                                cur_effs = char_rec.get("status_effects") if char_rec else []
                                if isinstance(cur_effs, str):
                                    try:
                                        cur_effs = json.loads(cur_effs)
                                    except Exception:
                                        cur_effs = [cur_effs] if cur_effs else []
                                if any(k in str(s).lower() for s in cur_effs for k in ("aroused", "breathless", "refractory", "satisfied", "spent")):
                                    cur_effs = [s for s in cur_effs if s and s not in ("[]", "{}", '""', "''") and not any(k in str(s).lower() for k in ("aroused", "breathless", "refractory", "satisfied", "spent"))]
                                    db.set_status_effects(u_lead, cur_effs)
                                    if isinstance(ch_lead, dict):
                                        ch_lead["status_effects"] = cur_effs
                                    _sync_char_outcome_status(ch_lead.get("name", player_name) if isinstance(ch_lead, dict) else player_name, cur_effs)
                        all_c_list = db.get_contacts(session_id) or [] if session_id else []
                        for c_full in all_c_list:
                            if isinstance(c_full, dict) and c_full.get("name"):
                                c_effs = c_full.get("status_effects") or []
                                if any(k in str(s).lower() for s in c_effs for k in ("aroused", "breathless", "refractory", "satisfied", "spent")):
                                    c_id = c_full.get("npc_id") or c_full.get("contact_id") or str(c_full.get("name")).lower().replace(" ", "_")
                                    c_effs = [s for s in c_effs if s and s not in ("[]", "{}", '""', "''") and not any(k in str(s).lower() for k in ("aroused", "breathless", "refractory", "satisfied", "spent"))]
                                    db.update_contact_status_effects(session_id, c_id, first_char_id, c_effs)
                                    _sync_companion_party_status(c_full.get("name"), c_effs)
                except Exception as e:
                    log.debug("Could not update refractory status on disengagement turn: %s", e)


    # 7. Downed / 0 HP character posture synchronization
    from mechanics.social.physical_state import _match_actor_key
    if party and isinstance(party, list):
        for entry in party:
            char = entry[0] if isinstance(entry, (tuple, list)) else entry
            if not isinstance(char, dict) or not char.get("name"):
                continue
            c_name = char["name"]
            matched_actor = _match_actor_key(c_name, updated_phys.get("actors", {}))
            if matched_actor in updated_phys.get("actors", {}):
                fresh_char = db.get_character(char.get("user_id", 0))
                if fresh_char and fresh_char.get("hp", 1) <= 0:
                    updated_phys["actors"][matched_actor]["posture"] = "Prone / Downed (Unconscious)"
                    updated_phys["actors"][matched_actor]["holding"] = "Dropped / Empty hands"
                    updated_phys["actors"][matched_actor]["stance"] = "Incapacitated"

    # Also synchronize recruited party companions
    for p_npc in ((session.get("party_npcs") or []) if session else []):
        if isinstance(p_npc, dict) and p_npc.get("name"):
            if p_npc.get("hp", 1) <= 0 or p_npc.get("current_hp", 1) <= 0:
                matched_p = _match_actor_key(p_npc["name"], updated_phys.get("actors", {}))
                if matched_p in updated_phys.get("actors", {}):
                    updated_phys["actors"][matched_p]["posture"] = "Prone / Downed (Unconscious)"
                    updated_phys["actors"][matched_p]["holding"] = "Dropped / Empty hands"
                    updated_phys["actors"][matched_p]["stance"] = "Incapacitated"

    # 8. Deceased character & fallen combatant posture synchronization
    deceased_raw = outcome.get("deceased_characters") or []
    dead_monsters_raw = outcome.get("dead_enemies") or outcome.get("dead_monsters") or []
    all_deceased = list(deceased_raw) + list(dead_monsters_raw)
    
    if "dropped_items" not in updated_phys:
        updated_phys["dropped_items"] = []
        
    for d_name in all_deceased:
        if d_name and isinstance(d_name, str):
            matched_dead = _match_actor_key(d_name.strip(), updated_phys.get("actors", {}))
            if matched_dead in updated_phys.get("actors", {}):
                held = updated_phys["actors"][matched_dead].get("holding", "")
                if held and held not in ("Empty hands", "Dropped / Empty hands", "Equipped weapon"):
                    if held not in updated_phys["dropped_items"]:
                        updated_phys["dropped_items"].append(held)
                updated_phys["actors"][matched_dead]["posture"] = "Deceased / Motionless"
                updated_phys["actors"][matched_dead]["holding"] = "Dropped / Empty hands"
                updated_phys["actors"][matched_dead]["stance"] = "Dead"

    # 9. Handle explicit search/loot action
    is_looting = False
    for a in actions:
        if isinstance(a, dict):
            act_text = str(a.get("label") or a.get("action") or a.get("text") or "").lower()
            if any(w in act_text for w in ("loot", "search", "gather spoils", "scavenge")):
                is_looting = True
                break
    if is_looting and updated_phys.get("dropped_items"):
        props_dict = updated_phys.setdefault("props", {})
        for item in updated_phys["dropped_items"]:
            target_k = item
            for existing_k in list(props_dict.keys()):
                if existing_k.lower() == item.lower():
                    target_k = existing_k
                    break
            props_dict[target_k] = "Dropped on the floor"
        updated_phys["dropped_items"] = []

    # 10. Handle explicit Redress action
    is_redressing = False
    for a in actions:
        if isinstance(a, dict):
            act_text = f"{a.get('label', '')} {a.get('action', '')} {a.get('text', '')}".lower()
            if any(w in act_text for w in ("redress", "get dressed", "put on clothes", "don clothes")):
                is_redressing = True
                break
    if is_redressing:
        from mechanics.social.physical_state import restore_equipped_outfit
        updated_phys = restore_equipped_outfit(updated_phys, party, scen_key=scen_key, session_id=session_id)

    # 11. Handle putting down carried burden or breaking free from physical restraint
    lead_char = party[0][0] if party and isinstance(party[0], (tuple, list)) else (party[0] if party and isinstance(party[0], dict) else None)
    if lead_char and lead_char.get("name") and updated_phys.get("actors"):
        from mechanics.social.physical_state import _match_actor_key, find_player_actor_key
        lead_key = find_player_actor_key(updated_phys["actors"], party=party, session_id=session_id) or _match_actor_key(lead_char["name"], updated_phys["actors"])
        if lead_key in updated_phys["actors"]:
            for a in actions:
                if isinstance(a, dict):
                    act_text = f"{a.get('label', '')} {a.get('action', '')} {a.get('text', '')}".lower()
                    # A. Putting down burden
                    if "put down" in act_text and any(w in act_text for w in ("carrying", "holding", "burden")):
                        old_tether = updated_phys["actors"][lead_key].pop("tether", None)
                        if old_tether:
                            carried_name = old_tether.replace("Carrying ", "").replace("carrying ", "").replace("holding ", "").strip()
                            if carried_name:
                                matched_c = _match_actor_key(carried_name, updated_phys["actors"])
                                if matched_c in updated_phys["actors"]:
                                    updated_phys["actors"][matched_c]["posture"] = "Resting safely on the ground"
                                    updated_phys["actors"][matched_c].pop("tether", None)
                    # B. Breaking free / slipping out of restraint on check success, or companion cutting bonds
                    elif any(w in act_text for w in ("break free", "slip out", "struggle", "cut", "untie", "free bonds", "companion_free")):
                        a_check = a.get("check")
                        from .core import is_check_success
                        if any(w in act_text for w in ("companion", "cut", "untie", "help")) or is_check_success(a_check, default_if_none=True):
                            updated_phys["actors"][lead_key].pop("tether", None)
                            updated_phys["actors"][lead_key]["tether_type"] = "none"
                            updated_phys["actors"][lead_key]["tether_partner"] = ""

    db.update_session_physical_state(session_id, updated_phys)
    outcome["_physical_state"] = updated_phys

    # 12. Post-turn choice reconciliation against updated_phys
    try:
        from mechanics.social.physical_state import is_erotic_intimate_contact as _post_is_erotic
        from mechanics.social.intimate_excitement import (
            build_intimate_choice_blueprints,
            has_state_contradiction_in_choice,
        )
        _upd_ic_str = str(updated_phys.get("intimate_contact", ""))
        _post_erotic = _post_is_erotic(_upd_ic_str)
        _pre_erotic = _post_is_erotic(str(current_phys.get("intimate_contact", "") if isinstance(current_phys, dict) else ""))
        _is_aftercare_now = "aftercare" in _upd_ic_str.lower()

        _ac_partners_list = []
        if _is_aftercare_now:
            _ac_partner = partner or ""
            if not _ac_partner and " with " in _upd_ic_str:
                _ac_partner = _upd_ic_str.split(" with ", 1)[1].split("(")[0].strip()

            _raw_ac_list = list(dps) if dps else ([_ac_partner] if _ac_partner else [])
            if len(_raw_ac_list) < 2 and " with " in _upd_ic_str:
                _ic_part_raw = _upd_ic_str.split(" with ", 1)[1].split("(")[0].strip()
                _ic_split = [
                    sp.strip()
                    for chunk in _ic_part_raw.split(",")
                    for sp in chunk.split(" and ")
                    if sp.strip() and sp.strip().lower() != "partner"
                ]
                if len(_ic_split) >= 2:
                    _raw_ac_list = _ic_split
                    _ac_partner = _ic_split[0]

            for _dp_item in _raw_ac_list:
                for _chunk in str(_dp_item).split(","):
                    for _sp in _chunk.split(" and "):
                        _clean_sp = _sp.strip()
                        if _clean_sp and _clean_sp not in _ac_partners_list:
                            _ac_partners_list.append(_clean_sp)
            if _ac_partners_list and (" and " in _ac_partner or "," in _ac_partner):
                _ac_partner = _ac_partners_list[0]

            # Multi-partner episodic memory and participatory affinity distribution
            if len(_ac_partners_list) >= 2:
                if "npc_memories" not in outcome or not isinstance(outcome["npc_memories"], list):
                    outcome["npc_memories"] = []
                existing_mem_npcs = {
                    str(m.get("npc_name", "")).lower()
                    for m in outcome["npc_memories"]
                    if isinstance(m, dict)
                }
                existing_ru_npcs = {
                    str(ru.get("npc_name") or ru.get("name") or "").lower().strip()
                    for ru in (outcome.get("relationship_updates") or [])
                    if isinstance(ru, dict)
                }
                for _p_name in _ac_partners_list:
                    if _p_name.lower() not in existing_mem_npcs:
                        _other = [x for x in _ac_partners_list if x != _p_name]
                        _other_str = " and ".join(_other)
                        _fact = (
                            f"Shared intimate encounter and sweet aftercare with {player_name} and {_other_str}."
                            if _other
                            else f"Shared intimate encounter and sweet aftercare with {player_name}."
                        )
                        outcome["npc_memories"].append({
                            "npc_name": _p_name,
                            "memory_fact": _fact,
                            "sentiment_delta": 3,
                            "importance": 2,
                            "is_secret": False,
                        })
                        existing_mem_npcs.add(_p_name.lower())
                    if _p_name.lower() not in existing_ru_npcs:
                        if "relationship_updates" not in outcome or not isinstance(outcome["relationship_updates"], list):
                            outcome["relationship_updates"] = []
                        outcome["relationship_updates"].append({
                            "npc_name": _p_name,
                            "delta_score": 2,
                            "track": "platonic",
                            "reasons": ["Participated in intimate group encounter."],
                        })
                        existing_ru_npcs.add(_p_name.lower())

        _existing_choices = outcome.get("choices") if outcome.get("choices") is not None else outcome.get("next_choices")
        if isinstance(_existing_choices, list) and _existing_choices:
            if _post_erotic:
                from game_engine.choices_cleaner import clean_choices_impl
                _dlg_p = (
                    outcome.get("dialogue_partners")
                    or outcome.get("dialogue_partner")
                    or (session.get("dialogue_partners") if isinstance(session, dict) else None)
                    or (session.get("dialogue_partner") if isinstance(session, dict) else None)
                    or partner
                )
                _loc_now = (
                    outcome.get("location")
                    or outcome.get("location_update")
                    or (session.get("current_location") if isinstance(session, dict) else "")
                    or (session.get("location") if isinstance(session, dict) else "")
                    or ""
                )
                if outcome.get("_hybrid_choices_built"):
                    _reconciled = game_engine.build_hybrid_turn_choices(
                        [dict(c) if isinstance(c, dict) else c for c in _existing_choices],
                        session=session,
                        party=party,
                        result=outcome,
                        actions=actions,
                    )
                else:
                    _reconciled = clean_choices_impl(
                        None,
                        choices=[dict(c) if isinstance(c, dict) else c for c in _existing_choices],
                        scenario=scen_key,
                        location=_loc_now,
                        char=lead_char,
                        dialogue_partner=_dlg_p,
                        session_id=session_id,
                    )
                if _reconciled:
                    if "choices" in outcome:
                        outcome["choices"] = _reconciled
                    if "next_choices" in outcome:
                        outcome["next_choices"] = _reconciled
            elif (_pre_erotic and not _post_erotic) or _is_aftercare_now:
                # Transitioned out of active intimacy (e.g. mutual climax -> aftercare, or disengagement):
                # Prune any leftover active climax/thrust/genital choices and offer aftercare + Redress if undressed.
                _stale_cues = (
                    "thrust", "drive deeper", "push over the edge", "push her over the edge",
                    "push him over the edge", "push them over the edge",
                    "through her tremors", "through his tremors", "through their tremors",
                    "spilling deep", "finish inside", "cum inside", "guide him inside", "pull him deep",
                    "quicken your pace", "relentless pace", "maintain a steady, deep rhythm",
                    "slide inside", "penetrat", "oral pace", "pleasures you with her mouth",
                    "pleasures you with his mouth", "pleasures you with their mouths",
                    "use your tongue", "rhythm of your tongue", "use your fingers to stroke",
                    "curl your fingers", "strokes you", "rhythm of her hand", "rhythm of his hand",
                    "rhythm of their hands", "gently withdraw", "pull back to catch your breath",
                    "push through exhaustion", "apologize breathlessly",
                )
                _climax_st_now = updated_phys.get("climax_state", {}) or {}
                _partner_climaxes_now = _climax_st_now.get("partner_climaxes") if isinstance(_climax_st_now, dict) else None
                _filtered = [
                    c for c in _existing_choices
                    if not (
                        isinstance(c, dict)
                        and (
                            any(k in str(c.get("label", "")).lower() for k in _stale_cues)
                            or has_state_contradiction_in_choice(
                                str(c.get("label", "")),
                                last_act="none",
                                partner_climaxed=True,
                                player_spent=True,
                                partner_climaxes=_partner_climaxes_now,
                                player_climaxed=True,
                            )
                        )
                    )
                ]
                if _is_aftercare_now:
                    _ac_partner_actors = []
                    _contacts_pool = []
                    if session_id:
                        try:
                            _contacts_pool = db.get_contacts(session_id) or []
                        except Exception:
                            _contacts_pool = []
                    if len(_ac_partners_list) >= 2:
                        _exc_act_map = (updated_phys.get("excitement", {}) or {}).get("actors", {}) or {}
                        _phys_act_map = updated_phys.get("actors", {}) or {}
                        for _p_name in _ac_partners_list:
                            _p_low = _p_name.lower().strip()
                            _p_first = (_p_low.split() or [""])[0]
                            _c_match = next(
                                (c for c in _contacts_pool if c.get("name", "").lower() == _p_low or (_p_first and len(_p_first) >= 3 and c.get("name", "").lower().startswith(_p_first))),
                                None
                            )
                            _c_spots = None
                            _c_gender = "Female"
                            if _c_match:
                                _c_gender = _c_match.get("gender") or (_c_match.get("appearance") or {}).get("gender") or "Female"
                                _c_appr = _c_match.get("appearance") or {}
                                if isinstance(_c_appr, dict) and (_c_appr.get("sensitive_spots_revealed") or _c_appr.get("turn_ons_revealed")):
                                    _c_spots = _c_appr.get("sensitive_spots")
                            _exc_k = _match_actor_key(_p_name, _exc_act_map) if _exc_act_map else ""
                            _phys_k = _match_actor_key(_p_name, _phys_act_map) if _phys_act_map else ""
                            _p_meter = int((_exc_act_map.get(_exc_k, {}) if _exc_k else {}).get("meter", 0) or 0)
                            _p_posture = str((_phys_act_map.get(_phys_k, {}) if _phys_k else {}).get("posture", ""))
                            _pc_k = _match_actor_key(_p_name, _partner_climaxes_now) if _partner_climaxes_now else ""
                            _ac_partner_actors.append({
                                "name": _p_name,
                                "meter": _p_meter,
                                "climaxed": bool(_partner_climaxes_now.get(_pc_k or _p_name, True)) if _partner_climaxes_now else True,
                                "posture": _p_posture,
                                "sensitive_spots": _c_spots,
                                "gender": _c_gender,
                            })

                    _single_p_gender = "Female"
                    if _ac_partner and _contacts_pool:
                        _ac_low = _ac_partner.lower().strip()
                        _ac_first = (_ac_low.split() or [""])[0]
                        _cm = next(
                            (c for c in _contacts_pool if c.get("name", "").lower() == _ac_low or (_ac_first and len(_ac_first) >= 3 and c.get("name", "").lower().startswith(_ac_first))),
                            None
                        )
                        if _cm:
                            _single_p_gender = _cm.get("gender") or (_cm.get("appearance") or {}).get("gender") or "Female"

                    _ac_bp = build_intimate_choice_blueprints(
                        partner_name=_ac_partner or "Partner",
                        player_climaxed=True,
                        premature_finish=False,
                        partner_actors=_ac_partner_actors if len(_ac_partner_actors) >= 2 else None,
                        partner_gender=_single_p_gender,
                    )
                    _existing_lbls = {
                        str(c.get("label", "")).lower()
                        for c in _filtered
                        if isinstance(c, dict)
                    }
                    for _fb_c in _ac_bp.get("choices", []):
                        if len(_filtered) >= 4:
                            break
                        if _fb_c["label"].lower() not in _existing_lbls:
                            _filtered.append(dict(_fb_c))
                            _existing_lbls.add(_fb_c["label"].lower())

                _undressed_kws = ("removed", "none", "naked", "nude", "stripped", "disheveled", "undone", "unbuttoned", "pulled aside")
                _actors_now = updated_phys.get("actors", {}) or {}
                for _entry in (party or []):
                    _ch = _entry[0] if isinstance(_entry, (tuple, list)) else _entry
                    if not isinstance(_ch, dict) or not _ch.get("name"):
                        continue
                    _cn = _ch["name"]
                    _mk = _match_actor_key(_cn, _actors_now)
                    if _mk in _actors_now:
                        _cl = _actors_now[_mk].get("clothing") or {}
                        if isinstance(_cl, dict):
                            _top_s = str(_cl.get("top", "")).lower()
                            _bot_s = str(_cl.get("bottom", "")).lower()
                            if any(u in _top_s or u in _bot_s for u in _undressed_kws):
                                if not any(isinstance(c, dict) and ("redress" in str(c.get("label", "")).lower() or "get dressed" in str(c.get("label", "")).lower()) for c in _filtered):
                                    _filtered.append({
                                        "label": f"Redress / Get dressed ({_cn})",
                                        "stat": "FREE",
                                        "requirement": 0,
                                        "category": "action",
                                        "action_category": "general_action",
                                    })
                                break
                if _filtered:
                    if "choices" in outcome:
                        outcome["choices"] = _filtered
                    if "next_choices" in outcome:
                        outcome["next_choices"] = _filtered
    except Exception:
        pass

  
    # ── Resolve Commitments from Arbiter ─────────────────────────────────────
    fulfilled_ids = outcome.get("fulfilled_commitments")
    broken_ids = outcome.get("broken_commitments")
    if fulfilled_ids or broken_ids:
        from db.memory import update_commitment_status
        for cid in (fulfilled_ids or []):
            if isinstance(cid, int) and cid > 0:
                update_commitment_status(session_id, cid, "fulfilled")
        for cid in (broken_ids or []):
            if isinstance(cid, int) and cid > 0:
                update_commitment_status(session_id, cid, "broken")
  
    # ── Resolve Entity Deaths from Arbiter ───────────────────────────────────
    deceased = outcome.get("deceased_characters")
    if deceased and isinstance(deceased, list):
        for name in deceased:
            if name and isinstance(name, str):
                bus.publish(NPCStatusChangedEvent(session_id=session_id, name=name.strip(), status="deceased"))
  
    # ── Resolve NPC Episodic Memory from Slim Narrator Schema ────────────────
    episodic_mem = outcome.get("episodic_memory")
    if episodic_mem and isinstance(episodic_mem, str) and episodic_mem.strip():
        from db.memory import add_npc_memory
        from mechanics.world.mobility import get_session_dialogue_partners
        current_turn = len(session.get("history") or []) if isinstance(session, dict) else 0
        mem_targets = list(outcome.get("dialogue_partners") or (get_session_dialogue_partners(session) if isinstance(session, dict) else []) or [])
        if not mem_targets and outcome.get("dialogue_partner"):
            mem_targets = [str(outcome["dialogue_partner"]).strip()]
        if not mem_targets:
            for npc_item in (outcome.get("npcs_present") or (session.get("current_npcs") if isinstance(session, dict) else []) or []):
                n_nm = npc_item.get("name") if isinstance(npc_item, dict) else str(npc_item)
                if n_nm and str(n_nm).strip() and str(n_nm).strip().lower() != "none":
                    mem_targets.append(str(n_nm).strip())
                    break
        for n_name in mem_targets[:2]:
            if n_name and str(n_name).strip():
                add_npc_memory(
                    session_id=session_id,
                    npc_name=str(n_name).strip(),
                    turn_index=current_turn,
                    memory_fact=episodic_mem.strip()[:300],
                    sentiment_delta=0,
                    importance=1,
                    is_secret=False,
                    emotional_tone="",
                    open_thread="",
                )

    # ── Resolve NPC Episodic Memories ────────────────────────────────────────
    npc_memories = outcome.get("npc_memories")
    if npc_memories and isinstance(npc_memories, list):
        from db.memory import add_npc_memory
        from db.social import update_contact_open_thread
        current_turn = len(session.get("history") or [])
        for m in npc_memories:
            if isinstance(m, dict) and m.get("npc_name") and m.get("memory_fact"):
                n_name = m["npc_name"].strip()
                emo = str(m.get("emotional_tone") or "").strip()
                thrd = str(m.get("open_thread") or "").strip()
                add_npc_memory(
                    session_id=session_id,
                    npc_name=n_name,
                    turn_index=current_turn,
                    memory_fact=m["memory_fact"].strip(),
                    sentiment_delta=m.get("sentiment_delta", 0),
                    importance=m.get("importance", 1),
                    is_secret=m.get("is_secret", False),
                    emotional_tone=emo,
                    open_thread=thrd,
                )
                if thrd or emo:
                    update_contact_open_thread(session_id=session_id, npc_id=n_name, open_thread=thrd, emotional_tone=emo)

def _reduce_entities_and_gifts(session_id: int, session: dict, outcome: dict, party: list, actions: list, is_combat: bool, scen_key: str):
    """Extracted Phase 2B Reducer for New Entities, Gifts, and Passive Regen."""
    import db, game_engine
    from mechanics.social.persona import normalize_appearance
    from mechanics.social.races import normalize_race
    from game_engine import get_combined_narrative
    # 1. Process pre-turn resolved gifts first (single-source-of-truth)
    pre_gifted = (outcome.get("_pre_turn_gifted") if isinstance(outcome, dict) else None) or []
    if pre_gifted:
        for g_entry in pre_gifted:
            if isinstance(g_entry, dict) and g_entry.get("user_id") and g_entry.get("item_name"):
                bus.publish(ItemGiftedEvent(
                    session_id=session_id,
                    user_id=g_entry["user_id"],
                    npc_name=g_entry.get("npc_name") or "NPC",
                    item_name=g_entry["item_name"],
                ))
    elif actions:
        # Legacy fallback when called outside pre-turn pipeline
        from mechanics.narrative.intent import classify_action_intent, IntentCategory
        for act in actions:
            if not isinstance(act, dict):
                continue
            act_label = act.get("label") or act.get("action", "")
            check_obj = act.get("check")
            check_succeeded = check_obj.succeeded if hasattr(check_obj, "succeeded") else (isinstance(check_obj, dict) and check_obj.get("succeeded", True) if check_obj else True)
            if not check_succeeded:
                continue
            parsed_intent = classify_action_intent(act_label)
            if parsed_intent.category == IntentCategory.GIFT_OFFER:
                u_id = act.get("user_id") or (party[0][0]["user_id"] if party else 0)
                gift_item_cand = parsed_intent.sub_target or parsed_intent.metadata.get("item_name", "")
                if u_id and gift_item_cand and gift_item_cand.lower() not in ("gift", "present"):
                    user_inv = db.get_inventory(u_id) or []
                    for inv_it in user_inv:
                        it_name = str(inv_it.get("name", "")).lower()
                        if gift_item_cand.lower() in it_name or it_name in gift_item_cand.lower():
                            bus.publish(ItemGiftedEvent(
                                session_id=session_id,
                                user_id=u_id,
                                npc_name=parsed_intent.target_entity or "NPC",
                                item_name=inv_it["name"]
                            ))
                            break
  
    # Anyone not mentioned still gets their passive regen during non-combat exploration.
    if not is_combat:
        mentioned = {co.get("name", "").lower() for co in outcome.get("character_outcomes", []) or [] if isinstance(co, dict)}
        for char, _ in party:
            if char["name"].lower() not in mentioned:
                db.apply_turn_regen(char["user_id"])
  
    first_char_id = party[0][0]["id"] if party else 0
    first_char_name = party[0][0].get("name", "Player") if party else "Player"
    # scen_key already fetched
  
    for entity in outcome.get("new_entities", []) or []:
        if not entity or not isinstance(entity, dict):
            continue
        ent_type = str(entity.get("type", "person") or "person")
        ent_name = str(entity.get("name", "") or "").strip()
        if not ent_name or ent_name.lower() == "none":
            continue
        import namegen
        if not namegen.is_valid_entity_name(ent_name) or namegen.is_collective_entity_name(ent_name):
            continue
        raw_race = entity.get("race") or "" if ent_type.lower() == "person" else ""
        norm_race = normalize_race(raw_race, scen_key=scen_key) if raw_race else raw_race
        raw_app = entity.get("appearance", {}) if ent_type.lower() == "person" else {}
        gender = entity.get("gender", "")
        norm_app = normalize_appearance(raw_app, gender=gender, race=norm_race or "human", scen_key=scen_key)
  
        import mechanics.social.persona as persona
        clean_desc = persona.sanitize_npc_description(entity.get("description", ""), norm_app)
        raw_turn_narrative = get_combined_narrative(outcome)
  
        disp_val = str(entity.get("disposition", "neutral")).lower()
        ent_faction = entity.get("faction") or entity.get("club") or ""
        db.upsert_lorebook_entity(
            session_id,
            ent_type,
            ent_name,
            clean_desc,
            disp_val,
            faction=ent_faction,
            traits=entity.get("traits", []),
            motivation=entity.get("motivation", ""),
            mannerisms=entity.get("mannerisms", ""),
            race=norm_race,
            appearance=norm_app,
        )
        if ent_type.lower() == "person" and ent_name:
            existing_c = db.get_contact(session_id, ent_name, first_char_id)
            party_npcs = db.get_session_party_npcs(session_id)
            party_names = {p.get("name", "").lower() for p in (party_npcs or [])}
            is_party = ent_name.lower() in party_names
            # Only existing contacts or party members get contacts table updates.
            # Ambient strangers and unrecruited NPCs remain in lorebook (World Codex) only.
            if existing_c or is_party:
                ent_binfo = {}
                if clean_desc:
                    ent_binfo["description"] = clean_desc
                for k in ("role", "occupation", "faction", "club", "club_role", "grade", "clique", "age", "location", "motivation", "mannerisms", "disposition"):
                    val = entity.get(k)
                    if val not in (None, "", "None", "Unknown", [], {}):
                        ent_binfo[k] = val
                db.upsert_contact(
                    session_id=session_id,
                    character_id=first_char_id,
                    npc_id=ent_name,
                    name=ent_name,
                    basic_info=ent_binfo if ent_binfo else None,
                    delta_score=0,
                    new_traits=entity.get("traits", []),
                    new_preferences=entity.get("preferences", []),
                    race=norm_race,
                    gender=gender,
                    appearance=norm_app,
                    narrative_text=raw_turn_narrative,
                )

def _reduce_media_capture(session_id: int, session: dict, party: list, outcome: dict, actions: list, scen_key: str, items_gained_by_user: dict):
    """Extracted Phase 2B Reducer for Smartphone Media Capture."""
    from mechanics.system.phone import scenario_has_smartphone
    from mechanics.narrative.intent import classify_action_intent, IntentCategory, IntentContext
    from mechanics.combat.items import create_digital_media_item
    if not scenario_has_smartphone(scen_key):
        return

    pre_media = (outcome.get("_pre_turn_media_captured") if isinstance(outcome, dict) else None) or []
    if pre_media:
        for m_entry in pre_media:
            if not isinstance(m_entry, dict):
                continue
            user_id = m_entry.get("user_id") or (party[0][0]["user_id"] if party else 0)
            if not user_id:
                continue
            media_type = str(m_entry.get("media_type") or "photo")
            subject = str(m_entry.get("subject") or "Scene")
            already_added = any(subject.lower() in str(it).lower() for it in items_gained_by_user.get(user_id, []))
            if not already_added:
                outcome_nar = outcome.get("outcome_narrative") or outcome.get("next_narrative") or f"Captured {media_type} of {subject}"
                caption_text = str(outcome_nar).split("\n")[0][:250].strip()
                item_id = create_digital_media_item(
                    user_id=user_id,
                    contact_name=subject,
                    media_type=media_type,
                    caption=caption_text,
                    subject=m_entry.get("location") or session.get("current_location", "Local Area"),
                    tags=["misc", "digital", "story"],
                )
                if item_id:
                    media_label = f"📸 Photo: {subject}" if "photo" in media_type else f"📹 Video: {subject}"
                    items_gained_by_user.setdefault(user_id, []).append(f"{media_label} (Saved to Photo Vault)")
        return

    # Legacy fallback when called outside pre-turn pipeline
    if actions:
        for act in actions:
            if not isinstance(act, dict):
                continue
            act_label = act.get("label") or act.get("action", "")
            check_obj = act.get("check")
            check_succeeded = check_obj.succeeded if hasattr(check_obj, "succeeded") else (isinstance(check_obj, dict) and check_obj.get("succeeded", True) if check_obj else True)
            if not check_succeeded:
                continue
  
            ctx = IntentContext(
                current_zone=session.get("current_location", ""),
                present_npcs=[n.get("name", "") for n in outcome.get("npcs_present", []) if isinstance(n, dict)],
                scenario=scen_key
            )
            parsed_intent = classify_action_intent(act_label, context=ctx)
            if parsed_intent.category == IntentCategory.MEDIA_CAPTURE:
                user_id = act.get("user_id") or (party[0][0]["user_id"] if party else 0)
                if user_id:
                    media_type = parsed_intent.metadata.get("media_type", "photo")
                    subject = parsed_intent.target_entity or "Scene"
                    already_added = any(subject.lower() in str(it).lower() for it in items_gained_by_user.get(user_id, []))
                    if not already_added:
                        outcome_nar = outcome.get("outcome_narrative") or outcome.get("next_narrative") or act_label
                        caption_text = outcome_nar.split("\n")[0][:250].strip()
                        item_id = create_digital_media_item(
                            user_id=user_id,
                            contact_name=subject,
                            media_type=media_type,
                            caption=caption_text,
                            subject=session.get("current_location", "Local Area"),
                            tags=["misc", "digital", "story"]
                        )
                        if item_id:
                            media_label = f"📸 Photo: {subject}" if "photo" in media_type else f"📹 Video: {subject}"
                            items_gained_by_user.setdefault(user_id, []).append(f"{media_label} (Saved to Photo Vault)")


from .core import get_combined_narrative
