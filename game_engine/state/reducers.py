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
import game_engine

from game_engine.core import CONFESSION_KEYWORDS, NPC_ORAL_RECEIVE_KEYWORDS, NPC_ORAL_GIVE_KEYWORDS, NPC_MANUAL_RECEIVE_KEYWORDS, NPC_MANUAL_GIVE_KEYWORDS, INTERCOURSE_KEYWORDS, KISS_KEYWORDS, DATE_KEYWORDS, ROMANCE_KEYWORDS
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
        format_milestone_memory,
        VALID_MILESTONE_EVENTS,
    )
    from mechanics.social.relationships import is_romantic_confession_intent

    current_intercourse = intercourse_exp or app_dict.get("intercourse_experience") or "virgin"
    current_oral = oral_exp or app_dict.get("oral_experience") or "inexperienced"
    current_manual = app_dict.get("manual_experience", "inexperienced")
    is_intimate_act = False
    new_mem = None
    delta_boost = 0

    npc_low = npc_name.lower().strip() if npc_name else ""
    npc_fst = npc_low.split()[0] if npc_low else ""

    if combined_check_text is None:
        combined_check_text = (
            " ".join(str(a.get("label", "")) for a in actions) + " " + narrative_text
        ).lower()

    # Pre-evaluate cues once to avoid redundant scans across large keyword tuples
    has_rec_cues = False
    has_give_cues = False
    has_m_rec = False
    has_m_give = False
    has_intercourse = False
    has_kiss = False
    has_date = False
    has_romance = False

    if overall_check_success:
        has_rec_cues = any(kw in combined_check_text for kw in NPC_ORAL_RECEIVE_KEYWORDS)
        has_give_cues = any(kw in combined_check_text for kw in NPC_ORAL_GIVE_KEYWORDS)
        has_m_rec = any(kw in combined_check_text for kw in NPC_MANUAL_RECEIVE_KEYWORDS)
        has_m_give = any(kw in combined_check_text for kw in NPC_MANUAL_GIVE_KEYWORDS)
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
        elif milestone_ev == "intercourse":
            if (is_player_oral_action or has_rec_cues or has_give_cues) and not is_player_intercourse_action:
                if has_give_cues and not has_rec_cues:
                    milestone_ev = "oral_give"
                else:
                    milestone_ev = "oral_receive"

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
        elif milestone_ev in ("first_kiss", "kiss"):
            _reveal_intimacy(milestone_ev)
            new_mem = format_milestone_memory(milestone_ev, first_char_name, custom_summary)
        elif milestone_ev == "confession":
            new_mem = format_milestone_memory("confession", first_char_name, custom_summary)
            _reveal_intimacy("confession")
            app_dict["demeanor_revealed"] = True
            track = "romantic"
        elif milestone_ev == "date":
            new_mem = format_milestone_memory("date", first_char_name, custom_summary)
            track = "romantic"

    # Tier 2: Secondary Engine Safety Net (Scoped to Target/Active Scene NPC)
    is_session_dp = bool(session and game_engine.is_dialogue_partner(npc_name, session=session))
    is_npc_target_of_action = any(
        (npc_low in str(a.get("label", "")).lower() or (len(npc_fst) >= 3 and npc_fst in str(a.get("label", "")).lower()))
        for a in actions
    ) or is_session_dp or single_update

    is_npc_target_of_confession = (
        (confession_target_npc and (npc_low == confession_target_npc.lower().strip() or npc_fst == (confession_target_npc.lower().split() or [""])[0]))
        or any((is_romantic_confession_intent(str(a.get("label", ""))) or any(kw in str(a.get("label", "")).lower() for kw in CONFESSION_KEYWORDS)) and (npc_low in str(a.get("label", "")).lower() or (len(npc_fst) >= 3 and npc_fst in str(a.get("label", "")).lower())) for a in actions)
        or (is_session_dp and is_player_confession_action)
    )

    if not new_mem and overall_check_success:
        is_pure_oral = (is_player_oral_action or has_rec_cues or has_give_cues) and not is_player_intercourse_action
        if is_player_intercourse_action or (has_intercourse and not is_pure_oral):
            current_intercourse = "non_virgin"
            app_dict["had_first_time_with_player"] = True
            new_mem = format_milestone_memory("intercourse", first_char_name, custom_summary)
            _reveal_intimacy("intercourse")
        elif (is_player_intimate_action or is_player_oral_action or has_rec_cues) and has_rec_cues:
            current_oral = transition_oral_experience(current_oral, "oral_receive")
            new_mem = format_milestone_memory("oral_receive", first_char_name, custom_summary)
            _reveal_intimacy("oral_receive")
        elif (is_player_intimate_action or is_player_oral_action or has_give_cues) and has_give_cues:
            current_oral = transition_oral_experience(current_oral, "oral_give")
            new_mem = format_milestone_memory("oral_give", first_char_name, custom_summary)
            _reveal_intimacy("oral_give")
        elif has_m_rec:
            current_manual = transition_manual_experience(current_manual, "manual_receive")
            new_mem = format_milestone_memory("manual_receive", first_char_name, custom_summary)
            _reveal_intimacy("manual_receive")
        elif has_m_give:
            current_manual = transition_manual_experience(current_manual, "manual_give")
            new_mem = format_milestone_memory("manual_give", first_char_name, custom_summary)
            _reveal_intimacy("manual_give")
        elif ((is_player_romantic_action and is_npc_target_of_action) or milestone_ev in ("first_kiss", "kiss")) and has_kiss:
            _reveal_intimacy(milestone_ev if milestone_ev in ("first_kiss", "kiss") else "kiss")
            new_mem = format_milestone_memory(milestone_ev if milestone_ev in ("first_kiss", "kiss") else "kiss", first_char_name, custom_summary)
        elif is_npc_target_of_confession or milestone_ev == "confession":
            new_mem = format_milestone_memory("confession", first_char_name, custom_summary)
            _reveal_intimacy("confession")
            app_dict["demeanor_revealed"] = True
            track = "romantic"
        elif ((is_player_romantic_action and is_npc_target_of_action) or milestone_ev == "date") and has_date:
            new_mem = format_milestone_memory("date", first_char_name, custom_summary)
            track = "romantic"
        elif is_player_affection_action and (affection_target_npc and (npc_low == affection_target_npc.lower().strip() or npc_fst == (affection_target_npc.lower().split() or [""])[0])):
            new_mem = format_milestone_memory("milestone", first_char_name, custom_summary) if custom_summary else f"Shared a tender, affectionate moment with {first_char_name}"
            delta_boost = 3
        elif gift_target_npc and (npc_low == gift_target_npc.lower().strip() or npc_fst == (gift_target_npc.lower().split() or [""])[0]):
            gift_label = gift_item_name or "a gift"
            new_mem = format_milestone_memory("milestone", first_char_name, custom_summary) if custom_summary else f"Received {gift_label} as a thoughtful gift from {first_char_name}"
        elif custom_summary:
            new_mem = format_milestone_memory("milestone", first_char_name, custom_summary)
        elif is_player_romantic_action and has_romance:
            new_mem = f"Romantic milestone shared with {first_char_name}"

        if is_npc_target_of_confession or milestone_ev == "confession":
            track = "romantic"

    return new_mem, current_intercourse, current_oral, current_manual, track, is_intimate_act, delta_boost

def _reduce_quests_and_waypoints(session_id: int, session: dict, party_uids: list, outcome: dict, actions: list, items_gained_by_user: dict):
    """Extracted Phase 2B Reducer for Quest and Waypoint Updates."""
    import db, game_engine
      # Process quest_updates array from OUTCOME_SCHEMA (primary, reliable path)
    quest_reward_notices = []
    completed_sub_quests = []
    newly_discovered_clues = []
    updated_quest_ids = set()
    for qu in outcome.get("quest_updates") or []:
        if not isinstance(qu, dict):
            continue
        qid = qu.get("quest_id")
        if qid:
            updated_quest_ids.add(qid)
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
            "⚡" in str(a.get("label", "")) or
            "climax" in str(a.get("label", "")).lower()
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
            for uid in party_uids:
                added_id = db.add_item(uid, ritem, "Quest Reward", "Reward from completed objective")
                if added_id is not None:
                    items_gained_by_user.setdefault(uid, []).append(ritem)
                else:
                    items_gained_by_user.setdefault(uid, []).append(f"{ritem} (Lost: Inventory Full!)")

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
      from character_data import sanitize_status_effects
      cleaned_status = sanitize_status_effects(status_raw)
      if not is_combat:
          # Clear temporary combat turn buffs when transitioning outside combat
          cleaned_status = [
              s for s in cleaned_status
              if not any(k in s for k in ("Iron Skin", "Aegis Warding", "Combat Booster", "Quickstep", "DT]", "DR]", "% ATK]", "% EVA]"))
              and not re.search(r"\[\d+\s*turns?\]", s, re.IGNORECASE)
          ]
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
      if not is_combat:
          db.apply_turn_regen(user_id)

def _reduce_factions(session_id: int, session: dict, outcome: dict, party: list, first_char_id: int):
    """Extracted Phase 2B Reducer for Faction Discoveries and Promotions."""
    import db, game_engine
    from scenario_data import is_mechanic_enabled
    _faction_scen_key = session.get("scenario", "fantasy") if session else "fantasy"
    from mechanics.social.factions import infer_default_hq_location
  
    faction_updates_list = list(outcome.get("faction_updates", []) or [])
  
    # Auto-detect faction discovery when player interacts with an affiliated contact
    for ru in outcome.get("relationship_updates", []) or []:
        c_name = str(ru.get("name") or ru.get("npc_name") or "").strip()
        if not c_name:
            continue
        c = db.get_contact(session_id, c_name.lower().replace(" ", "_"))
        if c:
            b = c.get("basic_info") or {}
            c_fac = str(b.get("faction") or b.get("faction_affiliation") or b.get("club") or c.get("faction") or "").strip()
            if c_fac and c_fac.lower() not in ("none", "unaligned", ""):
                existing_fnames = [str(f.get("faction_name") or f.get("name") or "").lower() for f in faction_updates_list]
                old_score = int(c.get("score", 0) or 0)
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
  
    # Handle faction promotion result from LLM
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
                    # Clear pending promotion from session
                    db.update_session(session_id, extra={"pending_promotion": None})

def _reduce_deterministic_waypoints(session_id: int, session: dict, outcome: dict, party_uids: list, actions: list):
    """Extracted Phase 2B Reducer for Deterministic Waypoint Triggers."""
    import db, game_engine
      # ---------------------------------------------------------------- Waypoint Progression Engine
    # 1. Deterministic Arrival Triggers
    from mechanics.world.waypoints import try_advance_on_arrival, try_complete_on_skill_check
    current_location = outcome.get("location") or (session.get("current_location") if session else "") or ""
    waypoint_notices = []
    advanced_this_turn = set()  # Track (qid, so_id) to prevent multi-stage cascading in a single action
  
    # We need to check all active quests & sub-objectives against current location
    active_quests = db.get_session_quests(session_id, status="Active")
    for q in active_quests:
        qid = q["quest_id"]
        # Check parent quest (e.g. Bounties)
        n = try_advance_on_arrival(session_id, qid, None, current_location)
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
        for so in q.get("sub_objectives", []):
            if isinstance(so, dict) and not so.get("completed"):
                so_id = so.get("id")
                if so_id is not None:
                    n = try_advance_on_arrival(session_id, qid, so_id, current_location)
                    if n:
                        waypoint_notices.append(n)
                        advanced_this_turn.add((qid, so_id))
                        break
  
    # Advance phone meetup appointments to 'arrived' when player reaches rendezvous location
    try:
        from mechanics.world.waypoints import check_location_matches_waypoint
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

    current_phys = db.get_session_physical_state(session_id)
    phys_updates = (
        outcome.get("physical_updates")
        or outcome.get("scene_state_updates")
        or outcome.get("physical_state_updates")
        or {}
    )

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
    is_combat = bool(outcome and (outcome.get("_combat_log") or outcome.get("_enemy_attack_notice") or game_engine.get_active_enemies(outcome) or game_engine.get_active_enemies(session)))
    if is_combat:
        updated_phys["intimate_contact"] = "none"
    else:
        updated_phys["combat_focus"] = "none"

    # 6. Automatic Intimate Contact inference & Disengagement Clearance
    if not phys_updates.get("intimate_contact") and not is_combat:
        is_disengagement = False
        # Physical separation / disengagement intent clears ongoing contact
        for a in (actions or []):
            a_label = ((a.get("label") or "") if isinstance(a, dict) else str(a)).lower()
            if any(k in a_label for k in (
                "step back", "step away", "pull back", "pull away", "let go", "break contact",
                "break the kiss", "break away", "excuse myself", "leave the room", "part ways",
                "goodbye", "farewell", "walk away", "turn away", "head out", "disengage"
            )):
                updated_phys["intimate_contact"] = "none"
                is_disengagement = True
                break

        # Dialogue partner switch clearance: if talking to a new NPC without referencing intimate partner, clear contact
        from mechanics.world.mobility import get_session_dialogue_partners
        dps = get_session_dialogue_partners(session)
        partner = dps[0] if dps else ""
        if dps and updated_phys.get("intimate_contact") not in ("none", ""):
            curr_ic = updated_phys["intimate_contact"].lower()
            if " with " in curr_ic:
                ic_target = curr_ic.split(" with ")[-1].strip().rstrip(")")
                if ic_target and partner.lower() not in ic_target and ic_target not in partner.lower():
                    act_text = " ".join(((a.get("label") or "") if isinstance(a, dict) else str(a)).lower() for a in (actions or []))
                    if ic_target not in act_text:
                        updated_phys["intimate_contact"] = "none"

        if not is_disengagement and updated_phys.get("intimate_contact") == "none":
            for rel in outcome.get("relationship_updates", []) or []:
                if isinstance(rel, dict) and rel.get("milestone_event"):
                    m_ev = str(rel["milestone_event"]).lower().strip()
                    npc_target = rel.get("npc_name", "partner")
                    if m_ev in ("first_kiss", "kiss"):
                        updated_phys["intimate_contact"] = f"Kissing / embrace with {npc_target}"
                        break
                    elif m_ev in ("oral_give", "oral_receive", "intercourse", "manual_give", "manual_receive"):
                        updated_phys["intimate_contact"] = f"Intimate encounter with {npc_target} ({m_ev.replace('_', ' ')})"
                        break
                    elif m_ev in ("cuddle", "cuddling", "embrace", "embracing"):
                        updated_phys["intimate_contact"] = f"Cuddling / embrace with {npc_target}"
                        break

            # Fallback: check actions for physical contact with dialogue partner
            if updated_phys.get("intimate_contact") == "none" and partner:
                for a in (actions or []):
                    a_label = ((a.get("label") or "") if isinstance(a, dict) else str(a)).lower()
                    if any(k in a_label for k in ("kiss", "kissing", "peck on")):
                        updated_phys["intimate_contact"] = f"Kissing with {partner}"
                        break
                    elif any(k in a_label for k in ("hold hands", "holding hands", "take her hand", "take his hand", "clasps hands", "holding her hand", "holding his hand")):
                        updated_phys["intimate_contact"] = f"Holding hands with {partner}"
                        break
                    elif any(k in a_label for k in ("cuddle", "cuddling", "embrace", "embracing", "hold close", "holding close")):
                        updated_phys["intimate_contact"] = f"Cuddling / embrace with {partner}"
                        break

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
            act_text = str(a.get("label") or a.get("action") or a.get("text") or "").lower()
            if any(w in act_text for w in ("redress", "get dressed", "put on clothes", "don clothes")):
                is_redressing = True
                break
    if is_redressing:
        from mechanics.social.physical_state import restore_equipped_outfit
        updated_phys = restore_equipped_outfit(updated_phys, party, scen_key=scen_key, session_id=session_id)

    # 11. Handle putting down carried burden or breaking free from physical restraint
    lead_char = party[0][0] if party and isinstance(party[0], (tuple, list)) else (party[0] if party and isinstance(party[0], dict) else None)
    if lead_char and lead_char.get("name") and updated_phys.get("actors"):
        from mechanics.social.physical_state import _match_actor_key
        lead_key = _match_actor_key(lead_char["name"], updated_phys["actors"])
        if lead_key in updated_phys["actors"]:
            for a in actions:
                if isinstance(a, dict):
                    act_text = str(a.get("label") or a.get("action") or a.get("text") or "").lower()
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
                    # B. Breaking free / slipping out of restraint on check success
                    elif any(w in act_text for w in ("break free", "slip out", "struggle to break")):
                        a_check = a.get("check")
                        from .core import is_check_success
                        if is_check_success(a_check, default_if_none=True):
                            updated_phys["actors"][lead_key].pop("tether", None)

    db.update_session_physical_state(session_id, updated_phys)
    outcome["_physical_state"] = updated_phys
  
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
  
    # ── Resolve NPC Episodic Memories ────────────────────────────────────────
    npc_memories = outcome.get("npc_memories")
    if npc_memories and isinstance(npc_memories, list):
        from db.memory import add_npc_memory
        current_turn = len(session.get("history") or [])
        for m in npc_memories:
            if isinstance(m, dict) and m.get("npc_name") and m.get("memory_fact"):
                add_npc_memory(
                    session_id=session_id,
                    npc_name=m["npc_name"].strip(),
                    turn_index=current_turn,
                    memory_fact=m["memory_fact"].strip(),
                    sentiment_delta=m.get("sentiment_delta", 0),
                    importance=m.get("importance", 1),
                    is_secret=m.get("is_secret", False)
                )

def _reduce_entities_and_gifts(session_id: int, session: dict, outcome: dict, party: list, actions: list, is_combat: bool, scen_key: str):
    """Extracted Phase 2B Reducer for New Entities, Gifts, and Passive Regen."""
    import db, game_engine
    from mechanics.social.persona import normalize_appearance
    from mechanics.social.races import normalize_race
    from game_engine import get_combined_narrative
      # Check if player gifted an inventory item
    if actions:
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
      # Check if the player performed a Media Capture action (e.g. took a photo/selfie/video) that succeeded
    if actions and scenario_has_smartphone(scen_key):
        from mechanics.narrative.intent import classify_action_intent, IntentCategory, IntentContext
        from mechanics.combat.items import create_digital_media_item
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
