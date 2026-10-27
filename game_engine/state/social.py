from __future__ import annotations
from typing import Dict, Any, List, Optional
from .constants import *
import mechanics.narrative.event_handlers
from mechanics.narrative.events import bus, LocationChangedEvent, NPCSpawnedEvent, NPCStatusChangedEvent, ItemGiftedEvent, ItemGainedEvent, FactionLeadershipChangedEvent, QuestCompletedEvent
import json
import re
import logging
import game_engine
import scenario_data

log = logging.getLogger(__name__)


def _resolve_player_social_impression_bonus(session: dict | None, party: list | None) -> tuple[int, str]:
    """
    Computes additive social/date affinity impression bonus from:
    1. Player's equipped Tier 2 (+2) or Tier 1 (+4) civilian fashion/accessories (`clothing.py`).
    2. Active Love Hotel suite ambiance (`Mirrored Velvet Suite` +1, `Rooftop Jacuzzi Suite` +3).
    """
    import db
    from mechanics.combat.items.clothing import get_equipped_clothing_affinity_bonus

    total_bonus = 0
    reasons_parts: list[str] = []

    inv: list = []
    if party:
        first_entry = party[0]
        if isinstance(first_entry, (tuple, list)) and len(first_entry) > 1 and isinstance(first_entry[1], list):
            inv = first_entry[1]
        else:
            p_char = first_entry[0] if isinstance(first_entry, (tuple, list)) else first_entry
            if isinstance(p_char, dict):
                if isinstance(p_char.get("inventory"), list):
                    inv = p_char["inventory"]
                elif p_char.get("user_id"):
                    try:
                        inv = db.get_inventory(int(p_char["user_id"])) or []
                    except Exception:
                        inv = []
    elif isinstance(session, dict):
        p_char = session.get("player_character")
        if isinstance(p_char, dict):
            if isinstance(p_char.get("inventory"), list):
                inv = p_char["inventory"]
            elif p_char.get("user_id"):
                try:
                    inv = db.get_inventory(int(p_char["user_id"])) or []
                except Exception:
                    inv = []

    outfit_bonus, outfit_name = get_equipped_clothing_affinity_bonus(inv)
    if outfit_bonus > 0:
        total_bonus += outfit_bonus
        reasons_parts.append(f"Stylish outfit: {outfit_name}")

    if isinstance(session, dict):
        loc_probe = f"{session.get('current_node_id', '')} {session.get('current_location', '')}".lower()
        if "sub_love_hotel_jacuzzi" in loc_probe or "rooftop jacuzzi suite" in loc_probe:
            total_bonus += 3
            reasons_parts.append("Rooftop Jacuzzi Suite ambiance")
        elif "sub_love_hotel_mirrored" in loc_probe or "mirrored velvet suite" in loc_probe:
            total_bonus += 1
            reasons_parts.append("Mirrored Velvet Suite ambiance")

    return total_bonus, " + ".join(reasons_parts)


def _reduce_social_and_milestones(session_id: int, session: dict, party: list, outcome: dict, actions: list, scen_key: str, items_gained_by_user: dict, first_char_id: int, first_char_name: str):
    """Extracted Phase 2B Reducer for Relationships, Milestones, and Escorts."""
    import db, game_engine, json, re
    from game_engine.core import (
        PLAYER_ROMANTIC_ACTION_KEYWORDS, PLAYER_INTIMATE_ACTION_KEYWORDS,
        PLAYER_ORAL_ACTION_KEYWORDS, PLAYER_INTERCOURSE_ACTION_KEYWORDS,
        matches_keyword_boundary
    )
    # Narrative text for context
    narrative_text = (str(outcome.get("outcome_narrative", "")) + " " + str(outcome.get("next_narrative", "")) + " " + str(outcome.get("narrative", ""))).lower()

    # Decrement recruitment and confession cooldowns for session
    db.decrement_recruitment_cooldowns(session_id)
    db.decrement_confession_cooldowns(session_id)
    db.decrement_contact_request_cooldowns(session_id)

    # Commit staged pre-turn social disclosures & commitment operations atomically (D3)
    _pre_social = (outcome.get("_pre_turn_social") if isinstance(outcome, dict) else None) or {}
    if session_id and isinstance(_pre_social, dict):
        for disc in (_pre_social.get("disclosed_appearances") or []):
            if not isinstance(disc, dict):
                continue
            try:
                d_npc_id = str(disc.get("npc_id") or "")
                d_name = str(disc.get("name") or "")
                d_app = disc.get("appearance")
                if d_npc_id and d_name and isinstance(d_app, dict):
                    db.upsert_contact(
                        session_id=session_id,
                        npc_id=d_npc_id,
                        name=d_name,
                        character_id=first_char_id,
                        delta_score=0,
                        appearance=d_app,
                    )
                    db.upsert_contact(
                        session_id=session_id,
                        npc_id=d_npc_id,
                        name=d_name,
                        character_id=0,
                        delta_score=0,
                        appearance=d_app,
                    )
            except Exception as _disc_err:
                log.warning("Failed committing staged disclosure: %s", _disc_err)

        staged_cm_ops = _pre_social.get("staged_commitment_ops") or []
        if staged_cm_ops:
            try:
                from db.memory import add_commitment
                from mechanics.system.commitments_engine import fulfill_commitment, flake_commitment, create_rendezvous
                for cm_op in staged_cm_ops:
                    if not isinstance(cm_op, dict):
                        continue
                    op_kind = cm_op.get("op")
                    if op_kind == "fulfill":
                        g_uid = int(cm_op.get("gold_deduct_uid") or 0)
                        g_amt = int(cm_op.get("gold_deduct_amount") or 0)
                        if g_uid and g_amt > 0:
                            c_char = db.get_character(g_uid, session_id=session_id) or {}
                            new_g = max(0, int(c_char.get("gold") or 0) - g_amt)
                            db.update_character_fields(g_uid, session_id=session_id, gold=new_g)
                        fulfill_commitment(session_id, int(cm_op["cid"]), current_turn=int(cm_op.get("turn") or 1))
                    elif op_kind == "flake":
                        flake_commitment(
                            session_id,
                            int(cm_op["cid"]),
                            reason=str(cm_op.get("reason") or "broken promise"),
                            current_turn=int(cm_op.get("turn") or 1),
                        )
                    elif op_kind == "create_rendezvous":
                        create_rendezvous(**(cm_op.get("kwargs") or {}))
                    elif op_kind == "add_commitment":
                        add_commitment(**(cm_op.get("kwargs") or {}))
            except Exception as _cm_err:
                log.warning("Failed committing staged commitment ops: %s", _cm_err)
  
    # Process Party Companion / Social Escort Recruitment & Dismissal
    from scenario_data import is_mechanic_enabled
    from mechanics.narrative.intent import (
        classify_action_intent,
        resolve_action_intent,
        IntentCategory,
        is_contact_exchange_action,
    )
    is_combat_scen = is_mechanic_enabled(scen_key, "tactical_combat")
    from mechanics.narrative.intent import is_escort_dismissal_action
    
    if not is_combat_scen:
        for a in (actions or []):
            a_label = str(a.get("label", ""))
            if is_escort_dismissal_action(a_label):
                curr_party = db.get_session_party_npcs(session_id)
                for p in curr_party:
                    if p.get("role") in ("Companion", "Friend", "Date", "Study Partner", "Classmate"):
                        db.remove_session_party_npc(session_id, p.get("name", ""))

    # Smartphone Contact Request / Phone Number Exchange
    for a in (actions or []):
        a_label = str(a.get("label", ""))
        a_parsed = resolve_action_intent(a)
        is_contact_req = (
            a_parsed.category == IntentCategory.PHONE_CONTACT_EXCHANGE
            or is_contact_exchange_action(a_label)
            or (any(kw in a_label.lower() for kw in ("contact info", "phone number", "line id")) and any(kw in a_label.lower() for kw in ("ask", "exchange", "request", "add")))
        )
        if is_contact_req:
            a_check = a.get("check")
            is_success = is_check_success(a_check, default_if_none=False)
            target_npc_name = a.get("target_npc") or a.get("combat_target") or a_parsed.target_entity
            if not target_npc_name:
                curr_npcs = session.get("current_npcs", []) if session else []
                for npc in curr_npcs:
                    n_name = game_engine._get_npc_name(npc)
                    if n_name and n_name.lower() != "none" and n_name.lower() in a_label.lower():
                        target_npc_name = n_name
                        break
            if not target_npc_name:
                from mechanics.world.mobility import get_session_dialogue_partners
                dps = get_session_dialogue_partners(session)
                if dps:
                    target_npc_name = dps[0]

            if target_npc_name:
                if is_success:
                    existing_c = db.get_contact(session_id, target_npc_name, first_char_id)
                    b_info = dict(existing_c.get("basic_info") or {}) if existing_c else {}
                    b_info["contact_added"] = True
                    b_info["is_contact"] = True
                    b_info["exchanged_contact"] = True
                    b_info["met_in_person"] = True
                    b_info.pop("offscreen_ripple_only", None)
                    db.upsert_contact(
                        session_id=session_id,
                        character_id=first_char_id,
                        npc_id=target_npc_name,
                        name=target_npc_name,
                        basic_info=b_info,
                        delta_score=8,
                        track="platonic",
                        new_general_memory=f"{target_npc_name} gave {first_char_name} their phone number and exchanged Line contact info."
                    )
                else:
                    db.set_contact_request_cooldown(session_id, target_npc_name, hours=24, until_next_day=True)
                    existing_c = db.get_contact(session_id, target_npc_name, first_char_id)
                    if existing_c:
                        db.upsert_contact(
                            session_id=session_id,
                            character_id=first_char_id,
                            npc_id=target_npc_name,
                            name=target_npc_name,
                            delta_score=-1,
                            new_general_memory=f"{target_npc_name} declined to share their contact info with {first_char_name} for now."
                        )
  
    for a in (actions or []):
        a_label = str(a.get("label", ""))
        a_parsed = resolve_action_intent(a)
        is_recruit = is_combat_scen and a_parsed.category == IntentCategory.PARTY_RECRUIT
        if is_recruit:
            a_check = a.get("check")
            is_success = is_check_success(a_check, default_if_none=False)
  
            # Identify target NPC from label or dialogue_partners or current_npcs
            target_npc_name = None
            curr_npcs = session.get("current_npcs", []) if session else []
            for npc in curr_npcs:
                n_name = game_engine._get_npc_name(npc)
                if n_name and n_name.lower() != "none" and (
                    matches_keyword_boundary(a_label.lower(), n_name.lower())
                    or (a_parsed.target_entity and n_name.lower() == a_parsed.target_entity.lower())
                    or (str(a.get("target_npc", "")).lower().strip() == n_name.lower())
                ):
                    target_npc_name = n_name
                    break
            if not target_npc_name and a_parsed.target_entity:
                target_npc_name = a_parsed.target_entity
            if not target_npc_name:
                from mechanics.world.mobility import get_session_dialogue_partners
                dps = get_session_dialogue_partners(session)
                if dps:
                    target_npc_name = dps[0]
  
            if target_npc_name:
                # Merchants and active hostile combat enemies cannot be recruited
                lore_ent = next((p for p in db.get_lorebook(session_id).get("person", []) if p.get("name", "").lower() == target_npc_name.lower()), {})
                t_role = str(lore_ent.get("role") or lore_ent.get("occupation") or "").lower()
                if any(m in t_role for m in ("merchant", "shopkeeper", "vendor", "apothecary")):
                    continue
                enemy_list = game_engine.get_active_enemies(session) or []
                if any(game_engine._get_npc_name(e).lower() == target_npc_name.lower() for e in enemy_list if e):
                    continue
                from mechanics.social.relationships import get_recruitment_cost
                contact_c = db.get_contact(session_id, target_npc_name, first_char_id)
                current_affinity = contact_c.get("relationship_score", 0) if contact_c else 0
                party_level = max(1, party[0][0].get("level", 1)) if (party and party[0]) else 1
                rec_cost = get_recruitment_cost(current_affinity, party_level)

                is_money_recruit = any(kw in a_label.lower() for kw in ("pay", "hire", "gold", "coin", "bribe", "contract", "salary", "wage", "money"))
                user_id = party[0][0]["user_id"] if (party and party[0]) else 0
                char_data = db.get_character(user_id) if user_id else None
                char_gold = char_data.get("gold", 0) if char_data else 0

                anom_extra_comp: dict = {}
                if scenario_data.is_anomalous_incursions_scenario(scen_key):
                    from mechanics.social.agent_roster import evaluate_anomalous_companion_recruitment
                    scene_ent = next(
                        (n for n in curr_npcs if isinstance(n, dict) and game_engine._get_npc_name(n).lower() == target_npc_name.lower()),
                        {},
                    )
                    cand_entity = dict(lore_ent or {})
                    if isinstance(scene_ent, dict):
                        cand_entity.update(scene_ent)
                    if isinstance(contact_c, dict):
                        cand_entity.update(contact_c)
                    cand_entity["name"] = target_npc_name
                    eval_res = evaluate_anomalous_companion_recruitment(
                        session or {"id": session_id, "scenario": scen_key},
                        user_id,
                        cand_entity,
                        current_affinity,
                        party_level,
                    )
                    if not eval_res.get("allowed"):
                        if eval_res.get("is_civilian_blocked"):
                            outcome["_civilian_recruit_blocked_notice"] = eval_res.get("reason")
                        else:
                            outcome["_companion_recruit_blocked_notice"] = eval_res.get("reason")
                            db.set_recruitment_cooldown(session_id, target_npc_name, turns=3)
                        continue
                    rec_cost = int(eval_res.get("cost", 0) or 0)
                    if rec_cost == 0:
                        # Free requisition / Friend standing in Anomalous Incursions succeeds if allowed (or skill check passed)
                        is_money_recruit = False
                        is_success = True
                    else:
                        is_money_recruit = True
                    anom_extra_comp = {
                        "anomalous_npc_tag": "special_agent",
                        "is_special_agent": True,
                        "agent_tier": eval_res.get("agent_tier", 1),
                        "rank_title": eval_res.get("rank_title", ""),
                        "agent_class": eval_res.get("agent_class", ""),
                        "faction_id": eval_res.get("faction_id", ""),
                        "faction_name": eval_res.get("faction_name", ""),
                        "innate_abilities": eval_res.get("innate_abilities", []),
                        "hp": eval_res.get("hp", 130),
                        "max_hp": eval_res.get("max_hp", 130),
                        "mp": eval_res.get("mp", 60),
                        "max_mp": eval_res.get("max_mp", 60),
                        "level": eval_res.get("level", party_level),
                        "stats": eval_res.get("stats", {}),
                        "weapon_profile": eval_res.get("weapon_profile", {}),
                    }

                can_afford = (char_gold >= rec_cost)
                recruitment_succeeded = can_afford if is_money_recruit else is_success

                if recruitment_succeeded:
                    if is_money_recruit and rec_cost > 0 and user_id:
                        db.apply_hp_mp_delta(user_id, gold_delta=-rec_cost)
                    party_npcs = db.get_session_party_npcs(session_id)
                    human_count = len(session.get("turn_order", [])) if session else 1
                    if human_count + len(party_npcs) < 4:
                        comp_hp = anom_extra_comp.get("hp") or (15 + party_level * 3 if is_combat_scen else 100)
                        comp_mp = anom_extra_comp.get("mp") or (10 + party_level * 2 if is_combat_scen else 100)
                        from mechanics.world.locations import resolve_companion_origin_location
                        origin_loc = resolve_companion_origin_location(session_id, session.get("current_location", "") if session else "", scen_key)
                        
                        lore_ent = next((p for p in db.get_lorebook(session_id).get("person", []) if p.get("name", "").lower() == target_npc_name.lower()), {})
                        role_desc = lore_ent.get("description", "Companion") or "Companion"
                        role_clean = anom_extra_comp.get("agent_class") or "Companion"
                        if not anom_extra_comp.get("agent_class"):
                            if is_combat_scen:
                                for cand in ["Scout", "Warrior", "Mage", "Cleric", "Rogue", "Paladin", "Archer", "Guard", "Scholar", "Alchemist", "Knight", "Assassin", "Mercenary"]:
                                    if cand.lower() in role_desc.lower() or cand.lower() in target_npc_name.lower():
                                        role_clean = cand
                                        break
                            else:
                                role_clean = "Friend"
                            
                        companion_data = {
                            "name": target_npc_name,
                            "role": role_clean,
                            "level": anom_extra_comp.get("level", party_level),
                            "hp": comp_hp,
                            "max_hp": anom_extra_comp.get("max_hp", comp_hp),
                            "mp": comp_mp,
                            "max_mp": anom_extra_comp.get("max_mp", comp_mp),
                            "status_effects": [],
                            "origin_location": origin_loc,
                            "race": lore_ent.get("race") or "",
                            "appearance": lore_ent.get("appearance_json", {}),
                            **anom_extra_comp,
                        }
                        db.add_session_party_npc(session_id, companion_data)
                        
                        new_curr_npcs = [n for n in curr_npcs if (n.get("name", "") if isinstance(n, dict) else str(n)).lower() != target_npc_name.lower()]
                        db.update_session_npcs(session_id, new_curr_npcs)
                        
                        rec_binfo = None
                        if anom_extra_comp.get("anomalous_npc_tag") == "special_agent":
                            rec_binfo = {
                                "anomalous_npc_tag": "special_agent",
                                "is_special_agent": True,
                                "agent_tier": anom_extra_comp.get("agent_tier", 1),
                                "rank_title": anom_extra_comp.get("rank_title", ""),
                                "agent_class": anom_extra_comp.get("agent_class", ""),
                                "faction_id": anom_extra_comp.get("faction_id", ""),
                                "faction": anom_extra_comp.get("faction_name", ""),
                                "innate_abilities": anom_extra_comp.get("innate_abilities", []),
                            }
                        db.upsert_contact(
                            session_id=session_id,
                            character_id=first_char_id,
                            npc_id=target_npc_name,
                            name=target_npc_name,
                            basic_info=rec_binfo,
                            delta_score=5,
                            track="platonic"
                        )
                else:
                    if not is_money_recruit:
                        db.set_recruitment_cooldown(session_id, target_npc_name, hours=24, until_next_day=True)
                    else:
                        db.set_recruitment_cooldown(session_id, target_npc_name, turns=3)
  
    # Auto-register all non-hostile scene NPCs into contacts
    if is_mechanic_enabled(scen_key, "contact_list") or is_mechanic_enabled(scen_key, "relationship_meter"):
        enemy_list = game_engine.get_active_enemies(outcome) or game_engine.get_active_enemies(session)
        enemy_names = {game_engine._get_npc_name(e).lower() for e in enemy_list if e}
        party_names = set()
        for c in (party or []):
            if isinstance(c, (list, tuple)) and c and isinstance(c[0], dict) and c[0].get("name"):
                party_names.add(str(c[0]["name"]).strip().lower())
            elif isinstance(c, dict) and c.get("name"):
                party_names.add(str(c["name"]).strip().lower())
        
        all_scene_npcs = list(outcome.get("npcs_present") or (session.get("current_npcs", []) if session else []))
        for ent in (outcome.get("new_entities") or []):
            if isinstance(ent, dict) and ent.get("type", "person").lower() == "person":
                all_scene_npcs.append(ent)
                
        from mechanics.world.mobility import get_session_dialogue_partners
        active_partners = get_session_dialogue_partners(outcome)
  
        raw_scene_narrative = get_combined_narrative(outcome)
  
        for npc in all_scene_npcs:
            n_name = game_engine._get_npc_name(npc)
            if not n_name or n_name.lower() == "none" or n_name.lower() in enemy_names or n_name.lower() in party_names:
                continue
  
            # Do not auto-add pure generic ambient crowd (e.g. "Drunken Patron", "Town Guard") unless spoken to or friendly
            from namegen import is_generic_role_name, is_collective_entity_name
            if is_collective_entity_name(n_name):
                continue
            disp = str(npc.get("disposition", "")).lower() if isinstance(npc, dict) else ""
            is_dialogue = game_engine.is_dialogue_partner(n_name, active_partners) or game_engine.is_dialogue_partner(n_name, [str(a.get("label", "")) for a in (actions or [])])
            if is_generic_role_name(n_name) and not is_dialogue and disp not in ("friendly", "companion", "ally"):
                continue
  
            n_role = (npc.get("role") if isinstance(npc, dict) else "") or ""
            n_desc = (npc.get("description") if isinstance(npc, dict) else "") or ""

            n_srt = (npc.get("social_role_type") if isinstance(npc, dict) else "") or ""
            promoted_parent = None
            if session_id:
                try:
                    import mechanics.social.genealogy as genealogy
                    promoted_parent = genealogy.maybe_promote_scene_parent(session_id, n_name)
                except Exception:
                    promoted_parent = None

            existing_c = db.get_contact(session_id, n_name, first_char_id)
            is_promoted_parent = bool(
                promoted_parent
                or (existing_c and (existing_c.get("household_role") in ("father", "mother") or (existing_c.get("basic_info") or {}).get("is_adult_family")))
            )
            # Check Peer / Role Eligibility (e.g. students vs teachers/parents/clerks in high school)
            import mechanics.social.relationships as relationships
            if not is_promoted_parent and not relationships.is_contact_eligible(name=n_name, role=n_role, description=n_desc, scenario=scen_key, session_id=session_id, social_role_type=n_srt):
                continue

            # Contacts require Friend tier (score >= 100), active party membership, or explicit contact_added
            from mechanics.social.relationships import is_unlocked_contact
            is_party = n_name.lower() in party_names
            if not is_party and not is_unlocked_contact(existing_c, party_names):
                continue
  
            n_traits = (npc.get("traits") if isinstance(npc, dict) else []) or []
            n_prefs = (npc.get("preferences") if isinstance(npc, dict) else []) or []
            n_race = (npc.get("race") if isinstance(npc, dict) else "") or ""
            n_gender = (npc.get("gender") if isinstance(npc, dict) else "") or ""
            n_app = (npc.get("appearance") if isinstance(npc, dict) else {}) or {}
            
            basic_info = {"met_in_person": True}
            if isinstance(npc, dict):
                for k in ("role", "occupation", "description", "faction", "club", "club_role", "grade", "clique", "age", "location", "mannerisms", "motivation", "disposition"):
                    val = npc.get(k)
                    if val not in (None, "", "None", "Unknown", [], {}):
                        basic_info[k] = val
            if scenario_data.is_anomalous_incursions_scenario(scen_key):
                try:
                    from mechanics.social.anomalous_npc_tags import classify_anomalous_npc_tag
                    t_tag = classify_anomalous_npc_tag(npc if isinstance(npc, dict) else {"name": n_name, "role": n_role, "description": n_desc}, session_id=session_id, scen_key=scen_key)
                    basic_info["anomalous_npc_tag"] = t_tag
                    basic_info["is_special_agent"] = (t_tag == "special_agent")
                except Exception:
                    pass
                
            db.upsert_contact(
                session_id=session_id,
                character_id=first_char_id,
                npc_id=n_name,
                name=n_name,
                basic_info=basic_info if basic_info else None,
                delta_score=0,
                track="platonic",
                new_traits=n_traits,
                new_preferences=n_prefs,
                race=n_race,
                gender=n_gender,
                appearance=n_app if n_app else None,
                narrative_text=raw_scene_narrative
            )
  
        # Deterministic Social Check & Dialogue Partner Affinity Fallback:
        existing_ru_names = {
            str(ru.get("npc_name") or ru.get("name") or "").lower().strip()
            for ru in (outcome.get("relationship_updates") or [])
            if isinstance(ru, dict)
        }
  
        for a in (actions or []):
            label = str(a.get("label", ""))
            label_low = label.lower()
            stat = str(a.get("stat", "NONE")).upper()
            a_check = a.get("check")
            tier = "success"
            if a_check:
                if hasattr(a_check, "tier") and a_check.tier is not None:
                    tier = str(a_check.tier).lower()
                elif isinstance(a_check, dict):
                    tier = str(a_check.get("tier", "success")).lower()
            overall_check_success = is_check_success(a_check, default_if_none=True)
  
            from mechanics.narrative.intent import is_dialogue_exit_action
            is_exit = is_dialogue_exit_action(a)
            if is_exit:
                continue
  
            target_npcs = []
            import mechanics.social.relationships as relationships
            for npc in all_scene_npcs:
                n_name = game_engine._get_npc_name(npc)
                if not n_name or n_name.lower() == "none" or n_name.lower() in party_names or n_name.lower() in enemy_names:
                    continue
                n_role = (npc.get("role") if isinstance(npc, dict) else "") or ""
                n_desc = (npc.get("description") if isinstance(npc, dict) else "") or ""
                if not relationships.is_contact_eligible(name=n_name, role=n_role, description=n_desc, scenario=scen_key):
                    continue
                if game_engine.is_dialogue_partner(n_name, [label]) or n_name.lower() in label_low:
                    if n_name not in target_npcs:
                        target_npcs.append(n_name)
  
            if not target_npcs and active_partners:
                for ap in active_partners:
                    if not relationships.is_contact_eligible(name=ap, scenario=scen_key):
                        continue
                    if game_engine.is_dialogue_partner(ap, [label]) or ap.lower() in label_low:
                        if ap not in target_npcs:
                            target_npcs.append(ap)
                if not target_npcs:
                    target_npcs.extend([ap for ap in active_partners if relationships.is_contact_eligible(name=ap, scenario=scen_key)])
  
            for t_npc in target_npcs:
                t_low = t_npc.lower().strip()
                from namegen import is_collective_entity_name
                if is_collective_entity_name(t_npc):
                    continue
                if not any(game_engine.is_dialogue_partner(t_npc, [ru_name]) for ru_name in existing_ru_names):
                    t_contact = db.get_contact(session_id, t_npc, first_char_id) if (session_id and first_char_id) else None
                    t_scene_npc = next((n for n in (all_scene_npcs or []) if isinstance(n, dict) and str(n.get("name", "")).strip().lower() == t_low), None)
                    from mechanics.social.affinity_engine import calculate_social_affinity_delta
                    _imp_b, _imp_r = _resolve_player_social_impression_bonus(session, party)
                    fb_delta, fb_reasons, _ = calculate_social_affinity_delta(
                        action=a,
                        npc_name=t_npc,
                        contact_data=t_contact or {},
                        scene_npc_data=t_scene_npc or {},
                        is_target_npc=True,
                        outcome_narrative=raw_scene_narrative,
                        social_impression_bonus=_imp_b,
                        social_impression_reason=_imp_r,
                    )

                    if "relationship_updates" not in outcome or not isinstance(outcome["relationship_updates"], list):
                        outcome["relationship_updates"] = []
                    outcome["relationship_updates"].append({
                        "npc_name": t_npc,
                        "delta_score": fb_delta,
                        "track": "platonic",
                        "reasons": fb_reasons,
                    })
                    existing_ru_names.add(t_low)
  
    # Strip any relationship updates for non-eligible NPCs (e.g. teachers/clerks/parents) or invalid names, and filter by witness presence
    import mechanics.social.relationships as relationships
    from namegen import is_valid_entity_name
    
    # Perspective Filtering: Only NPCs present in this turn can receive relationship updates or memories.
    # Enforce only when we have reliable NPC-presence information from the outcome or session.
    raw_npcs_present = outcome.get("npcs_present")
    if raw_npcs_present is not None:
        # LLM explicitly provided the list — always enforce against this list
        enforce_perspective = True
        present_npc_names = {game_engine._get_npc_name(n).lower() for n in (raw_npcs_present or []) if game_engine._get_npc_name(n)}
    else:
        # Key was omitted by LLM — fall back to session's known current NPCs if available
        session_npcs = (session.get("current_npcs") or []) if session else []
        if session_npcs:
            enforce_perspective = True
            present_npc_names = {game_engine._get_npc_name(n).lower() for n in session_npcs if game_engine._get_npc_name(n)}
        else:
            # No reliable presence data at all — skip enforcement to avoid dropping legitimate updates
            enforce_perspective = False
            present_npc_names = set()
    # Also include freshly spawned new_entities — they are physically present even if not in npcs_present
    for ent in (outcome.get("new_entities") or []):
        if isinstance(ent, dict) and ent.get("type", "person").lower() == "person":
            ent_name = game_engine._get_npc_name(ent)
            if ent_name:
                present_npc_names.add(ent_name.lower())
                
    # CRITICAL: Always include active party companions. The LLM often omits them from npcs_present
    # because it thinks of them as "party" rather than "NPCs". They are always physically present.
    if party_names:
        present_npc_names.update(party_names)


    
    cleaned_rel_updates = []
    seen_rel_map = {}
    for rel in (outcome.get("relationship_updates") or []):
        if not isinstance(rel, dict):
            continue
        # Clean up malformed or escaped JSON keys in rel dict
        clean_rel = {}
        for k, v in rel.items():
            k_str = str(k).strip()
            if '"' in k_str or len(k_str) > 60:
                continue
            clean_rel[k_str] = v
        rel = clean_rel

        r_name = str(rel.get("npc_name") or rel.get("name") or "").strip()
        import namegen
        if not is_valid_entity_name(r_name) or namegen.is_collective_entity_name(r_name):
            continue
            
        if enforce_perspective and r_name.lower() not in present_npc_names:
            log.warning(f"Perspective Filter triggered: Dropping relationship update for {r_name} because they were not present in the scene.")
            continue
            
        r_role = rel.get("role", "")
        r_desc = rel.get("description", "")
        r_srt = rel.get("social_role_type", "")
        if not r_role or not r_desc or not r_srt:
            for npc in (all_scene_npcs or []):
                if isinstance(npc, dict) and str(npc.get("name", "")).strip().lower() == str(r_name).strip().lower():
                    r_role = r_role or npc.get("role", "")
                    r_desc = r_desc or npc.get("description", "")
                    r_srt = r_srt or npc.get("social_role_type", "")
                    break
        existing_r_c = db.get_contact(session_id, r_name, first_char_id) if session_id else None
        is_r_promoted_parent = bool(
            existing_r_c
            and (
                existing_r_c.get("household_role") in ("father", "mother")
                or (existing_r_c.get("basic_info") or {}).get("is_adult_family")
            )
        )
        if r_name and not is_r_promoted_parent and not relationships.is_contact_eligible(name=r_name, role=r_role, description=r_desc, scenario=scen_key, session_id=session_id, social_role_type=r_srt):
            continue

        import namegen
        r_key = r_name.lower()
        r_first = (r_key.split() or [""])[0]
        r_given = namegen.extract_first_and_last_name(r_name)[0].lower().strip()
        r_tokens = {t for t in (r_first, r_given) if len(t) >= 3 and t not in namegen.NAME_PARTICLES_AND_HONORIFICS}
        matched_k = None
        for k in seen_rel_map:
            if k == r_key:
                matched_k = k
                break
            k_first = (k.split() or [""])[0]
            k_given = namegen.extract_first_and_last_name(k)[0].lower().strip()
            k_tokens = {t for t in (k_first, k_given) if len(t) >= 3 and t not in namegen.NAME_PARTICLES_AND_HONORIFICS}
            if r_tokens & k_tokens:
                matched_k = k
                break

        if matched_k:
            existing = seen_rel_map[matched_k]
            # Merge traits
            for trait in (rel.get("new_traits") or []):
                ex_traits = existing.setdefault("new_traits", [])
                if trait and trait not in ex_traits:
                    ex_traits.append(trait)
            # Merge preferences
            for pref in (rel.get("new_preferences") or []):
                ex_prefs = existing.setdefault("new_preferences", [])
                if pref and pref not in ex_prefs:
                    ex_prefs.append(pref)
            # Merge revealed attributes
            rev_attrs = rel.get("revealed_attributes") or []
            if rev_attrs:
                ex_attrs = existing.setdefault("revealed_attributes", [])
                for a in (rev_attrs if isinstance(rev_attrs, list) else [rev_attrs]):
                    if a and a not in ex_attrs:
                        ex_attrs.append(a)
            # Merge boolean revealed flags
            for k, v in rel.items():
                if str(k).endswith("_revealed") and v is True:
                    existing[k] = True
            # Merge track / milestone / memory
            if rel.get("track") == "romantic":
                existing["track"] = "romantic"
            if rel.get("milestone_event") and not existing.get("milestone_event"):
                existing["milestone_event"] = rel["milestone_event"]
            if rel.get("memory_summary") and not existing.get("memory_summary"):
                existing["memory_summary"] = rel["memory_summary"]
            continue

        seen_rel_map[r_key] = rel
        cleaned_rel_updates.append(rel)
    outcome["relationship_updates"] = cleaned_rel_updates
  
    from mechanics.social.persona import generate_past_intimate_history, format_milestone_memory, VALID_MILESTONE_EVENTS
  
    # Determine if overall player action check was successful
    overall_check_success = True
    for a in actions:
        a_check = a.get("check")
        if a_check:
            if not is_check_success(a_check, default_if_none=True):
                overall_check_success = False
  
    # Check player action intent
    is_player_romantic_action = False
    is_player_intimate_action = False
    is_player_oral_action = False
    is_player_intercourse_action = False
    is_player_confession_action = False
    is_player_affection_action = False
    affection_target_npc = None
    gift_target_npc = None
    gift_item_name = None
    confession_target_npc = None
    from mechanics.social.relationships import is_romantic_confession_intent
    from mechanics.narrative.intent import classify_action_intent, IntentCategory, IntentContext
    for a in actions:
        a_lbl = str(a.get("label", ""))
        a_chk = a.get("check")
        chk_ok = is_check_success(a_chk, default_if_none=True)
        
        sess = session or {}
        from mechanics.world.mobility import get_session_dialogue_partners
        _sess_dps = get_session_dialogue_partners(sess)
        ctx_a = IntentContext(
            dialogue_partner=_sess_dps[0] if _sess_dps else "",
            dialogue_partners=_sess_dps,
            current_zone=sess.get("current_location", ""),
            present_npcs=[game_engine._get_npc_name(n) for n in (sess.get("current_npcs") or []) if n],
            scenario=scen_key
        )
        parsed_a = resolve_action_intent(a, ctx_a)
  
        _primary_dp = _sess_dps[0] if _sess_dps else None
        # Check Layer 1, 2, 3 confession intent
        is_conf = (a.get("intent") == "romantic_confession") or (parsed_a.category == IntentCategory.ROMANTIC_CONFESSION) or is_romantic_confession_intent(a_lbl)
        if is_conf:
            target_cand = a.get("target_npc") or parsed_a.target_entity or _primary_dp
            confession_target_npc = target_cand
            if chk_ok:
                is_player_confession_action = True
                is_player_romantic_action = True
            else:
                # Failed confession check -> 3-turn cooldown to prevent repetitive spam
                if session_id and target_cand:
                    db.set_confession_cooldown(session_id, target_cand, turns=3)
  
        # Check Affection Touch intent
        if parsed_a.category == IntentCategory.AFFECTION_TOUCH:
            affection_target_npc = a.get("target_npc") or parsed_a.target_entity or _primary_dp
            if chk_ok:
                is_player_affection_action = True
                is_player_romantic_action = True
  
        # Check Gift Offer intent
        if parsed_a.category == IntentCategory.GIFT_OFFER or a.get("sub_intent") == "gift_offer":
            gift_target_npc = a.get("target_npc") or parsed_a.target_entity or _primary_dp
            gift_item_name = parsed_a.sub_target or parsed_a.metadata.get("item_name", "Gift")
  
        # Check Intimate Act intent
        a_sub = str(a.get("sub_intent") or parsed_a.sub_target or "").lower()
        if parsed_a.category == IntentCategory.INTIMATE_ACT or a_sub in ("intercourse", "oral_give", "oral_receive", "anal_give", "anal_receive"):
            if chk_ok:
                is_player_intimate_action = True
                if a_sub == "intercourse":
                    is_player_intercourse_action = True
                elif a_sub in ("oral_give", "oral_receive"):
                    is_player_oral_action = True
                elif a_sub in ("anal_give", "anal_receive"):
                    is_player_intimate_action = True
  
        if chk_ok:
            if matches_keyword_boundary(a_lbl, PLAYER_ROMANTIC_ACTION_KEYWORDS, allow_negated=False) or is_conf:
                is_player_romantic_action = True
            if matches_keyword_boundary(a_lbl, PLAYER_INTIMATE_ACTION_KEYWORDS, allow_negated=False):
                is_player_intimate_action = True
            is_oral_act = matches_keyword_boundary(a_lbl, PLAYER_ORAL_ACTION_KEYWORDS, allow_negated=False) or (a_sub in ("oral_give", "oral_receive"))
            if is_oral_act:
                is_player_oral_action = True
                is_player_intimate_action = True
            is_anal_act = (a_sub in ("anal_give", "anal_receive")) or matches_keyword_boundary(a_lbl, ("anal", "ass", "pegged", "pegging", "backdoor"), allow_negated=False)
            if is_anal_act:
                is_player_intimate_action = True
            has_explicit_penetration = matches_keyword_boundary(a_lbl, ("dick", "cock", "shaft", "penis", "have sex", "make love", "penetrate", "fuck", "creampie", "breed"), allow_negated=False)
            if matches_keyword_boundary(a_lbl, PLAYER_INTERCOURSE_ACTION_KEYWORDS, allow_negated=False) or a_sub == "intercourse":
                if (not is_oral_act and not is_anal_act) or (has_explicit_penetration and not is_anal_act):
                    is_player_intercourse_action = True
  
    # Process explicit relationship updates from LLM outcome
    narrative_text = get_combined_narrative(outcome)
    _pre_intimate_info = (outcome.get("_pre_turn_intimacy") if isinstance(outcome, dict) else None) or {}
    _pre_act_classified = str((_pre_intimate_info.get("action_classified") or {}).get("act_type") or "").lower()
    _has_pre_turn_pipeline = isinstance(outcome, dict) and (
        outcome.get("_pre_turn_social") is not None or outcome.get("_pre_turn_intimacy") is not None
    )
    _block_prose_milestone_scrape = bool(
        _has_pre_turn_pipeline
        and _pre_act_classified in ("", "none", "foreplay_nongenital")
        and not (is_player_intercourse_action or is_player_oral_action or is_player_intimate_action)
    )
    if _block_prose_milestone_scrape:
        # Pre-turn deterministic pipeline verified this turn is NOT an explicit sexual act;
        # do not allow LLM narrative metaphors to trigger false virginity/experience milestones.
        combined_check_text = " ".join(str(a.get("label", "")) for a in actions).lower()
    else:
        combined_check_text = (
            " ".join(str(a.get("label", "")) for a in actions) + " " + narrative_text
        ).lower()
    processed_npcs = set()
    for idx, rel in enumerate(outcome.get("relationship_updates", []) or []):
        if not isinstance(rel, dict):
            continue
        rel = {str(k).strip(): v for k, v in rel.items()}
        outcome["relationship_updates"][idx] = rel
        npc_name = rel.get("npc_name") or rel.get("name")
        if npc_name and is_valid_entity_name(npc_name):
            import namegen
            n_low = npc_name.lower().strip()
            n_first = (n_low.split() or [""])[0]
            n_given = namegen.extract_first_and_last_name(npc_name)[0].lower().strip()
            n_tokens = {t for t in (n_first, n_given) if len(t) >= 3 and t not in namegen.NAME_PARTICLES_AND_HONORIFICS}

            # Check whether any action explicitly names or targets specific character(s)
            action_explicit_targets = set()
            for a in (actions or []):
                t_npc = str(a.get("target_npc") or a.get("combat_target") or "").lower().strip()
                if t_npc:
                    action_explicit_targets.add(t_npc)
                lbl_low = str(a.get("label") or a.get("text") or "").lower()
                for sn in (all_scene_npcs or []):
                    sn_name = str(sn.get("name") if isinstance(sn, dict) else sn).lower().strip()
                    sn_first = (sn_name.split() or [""])[0]
                    if sn_name and (matches_keyword_boundary(lbl_low, sn_name) or (len(sn_first) >= 3 and matches_keyword_boundary(lbl_low, sn_first))):
                        action_explicit_targets.add(sn_name)

            is_directly_addressed = any(
                (matches_keyword_boundary(str(a.get("label", "")).lower(), n_low) or any(matches_keyword_boundary(str(a.get("label", "")).lower(), tok) for tok in n_tokens))
                or (str(a.get("target_npc", "")).lower().strip() in ({n_low} | n_tokens))
                for a in (actions or [])
            )

            is_special_target = bool(
                (confession_target_npc and (n_low == confession_target_npc.lower().strip() or bool(n_tokens & {(confession_target_npc.lower().split() or [""])[0], namegen.extract_first_and_last_name(confession_target_npc)[0].lower().strip()})))
                or (affection_target_npc and (n_low == affection_target_npc.lower().strip() or bool(n_tokens & {(affection_target_npc.lower().split() or [""])[0], namegen.extract_first_and_last_name(affection_target_npc)[0].lower().strip()})))
                or (gift_target_npc and (n_low == gift_target_npc.lower().strip() or bool(n_tokens & {(gift_target_npc.lower().split() or [""])[0], namegen.extract_first_and_last_name(gift_target_npc)[0].lower().strip()})))
            )

            # Determine whether npc_name is an active participant / target of the player's action
            if action_explicit_targets:
                is_target_npc = is_directly_addressed or is_special_target
            else:
                is_target_npc = (
                    is_directly_addressed
                    or bool(session and game_engine.is_dialogue_partner(npc_name, session=session))
                    or is_special_target
                )

            # Determine whether player's action towards this NPC was hostile
            hostile_keywords = (
                "attack", "punch", "strike", "slap", "shove", "kick", "stab", "shoot",
                "insult", "mock", "belittle", "humiliate", "threaten", "intimidate",
                "steal", "rob", "pickpocket", "poison", "betray"
            )
            is_hostile_action = any(
                matches_keyword_boundary(str(a.get("label", "")).lower(), hostile_keywords, allow_negated=False)
                for a in (actions or [])
                if (matches_keyword_boundary(str(a.get("label", "")).lower(), n_low) or (len(n_first) >= 3 and matches_keyword_boundary(str(a.get("label", "")).lower(), n_first)) or str(a.get("target_npc", "")).lower().strip() in (n_low, n_first))
            )

            # Find matching action for check evaluation
            primary_action = None
            for a in (actions or []):
                if matches_keyword_boundary(str(a.get("label", "")).lower(), n_low) or (len(n_first) >= 3 and matches_keyword_boundary(str(a.get("label", "")).lower(), n_first)) or str(a.get("target_npc", "")).lower().strip() in (n_low, n_first):
                    primary_action = a
                    break
            if not primary_action and actions:
                primary_action = actions[0]

            contact = db.get_contact(session_id, npc_name, first_char_id) if (session_id and first_char_id) else None
            target_scene_npc = None
            for npc in (all_scene_npcs or []):
                if isinstance(npc, dict) and str(npc.get("name", "")).strip().lower() == n_low:
                    target_scene_npc = npc
                    break

            eval_contact = dict(contact) if contact else {}
            if rel.get("new_traits"):
                eval_contact["traits"] = list(eval_contact.get("unlocked_traits") or eval_contact.get("traits") or []) + list(rel["new_traits"])
            if rel.get("new_preferences"):
                eval_contact["preferences"] = list(eval_contact.get("preferences") or []) + list(rel["new_preferences"])

            eval_action = dict(primary_action) if primary_action else {}
            if gift_item_name and not eval_action.get("item_name"):
                eval_action["item_name"] = gift_item_name
            if rel.get("delta_score") is not None:
                eval_action["suggested_delta"] = rel.get("delta_score")
            if rel.get("interaction_tone") is not None:
                eval_action["interaction_tone"] = rel.get("interaction_tone")
            if rel.get("trait_alignment") is not None:
                eval_action["trait_alignment"] = rel.get("trait_alignment")

            if (not actions or rel.get("_pre_turn_resolved")) and rel.get("delta_score") is not None:
                delta = int(rel.get("delta_score"))
                aff_reasons = ["Pre-turn deterministic social resolution"] if rel.get("_pre_turn_resolved") else ["Direct outcome update"]
                aff_breakdown = {"base_delta": delta}
            else:
                from mechanics.social.affinity_engine import calculate_social_affinity_delta
                from mechanics.social.conversation_choices import (
                    resolve_partner_conversation_profile,
                    get_partner_conversation_budget_state,
                    is_non_quest_social_turn_action,
                )
                _post_prof = resolve_partner_conversation_profile(session, npc_name, party=party, current_npcs=all_scene_npcs)
                _post_bstate = get_partner_conversation_budget_state(session, _post_prof)
                if _post_prof.get("is_private_meetup"):
                    eval_action["is_private_meetup"] = True
                _imp_b, _imp_r = _resolve_player_social_impression_bonus(session, party)
                delta, aff_reasons, aff_breakdown = calculate_social_affinity_delta(
                    action=eval_action,
                    npc_name=npc_name,
                    contact_data=eval_contact,
                    scene_npc_data=target_scene_npc or {},
                    is_target_npc=is_target_npc,
                    outcome_narrative=narrative_text,
                    social_impression_bonus=_imp_b,
                    social_impression_reason=_imp_r,
                )
                _eval_int = str(eval_action.get("intent") or "").lower().strip()
                if (
                    delta > 0
                    and (
                        eval_action.get("_post_budget_zero_affinity")
                        or (
                            not eval_action.get("_within_social_budget")
                            and int(_post_bstate.get("remaining_budget", 3)) <= 0
                            and is_non_quest_social_turn_action(eval_action, was_already_partner=True)
                        )
                    )
                    and _eval_int not in ("romantic_confession", "phone_contact_exchange", "gift_offer", "intimate_act")
                ):
                    delta = 0
                    aff_reasons.append("Daily small-talk budget exhausted (0)")
            rel["delta_score"] = delta
            rel["reasons"] = aff_reasons
            log.info("Deterministic Social Affinity for %s: delta=%d, breakdown=%s, reasons=%s", npc_name, delta, aff_breakdown, aff_reasons)

            traits = rel.get("new_traits", []) or []
            prefs = rel.get("new_preferences", []) or []
            track = str(rel.get("track", "")).strip().lower()
            intercourse_exp = rel.get("intercourse_experience", "")
            oral_exp = rel.get("oral_experience", "")
            intimate_rev = rel.get("intimate_revealed", False)
            milestone_ev = str(rel.get("milestone_event", "")).lower().strip()
            custom_summary = rel.get("memory_summary") or rel.get("new_memory") or rel.get("memory")

            existing_track = (str(contact.get("track") or "").strip().lower() if contact else "") or "platonic"

            is_confession_target_npc = (
                bool(confession_target_npc and (n_low == confession_target_npc.lower().strip() or n_first == (confession_target_npc.lower().split() or [""])[0]))
                or any(
                    (is_romantic_confession_intent(str(a.get("label", ""))) or a.get("intent") == "romantic_confession")
                    and (n_low in str(a.get("label", "")).lower() or (len(n_first) >= 3 and bool(re.search(rf"\b{re.escape(n_first)}\b", str(a.get("label", "")).lower()))))
                    for a in (actions or [])
                )
                or (not confession_target_npc and is_target_npc)
            )

            # Strict romance track guard: Intimacy, casual inquiry, or flirting alone
            # must NEVER promote 'platonic' track to 'romantic' without an explicit
            # romantic confession/proposal or date milestone event at score >= 100.
            has_date_intent = (
                milestone_ev in ("confession", "date")
                or any(
                    str(a.get("sub_intent") or "").lower().strip() in ("confession", "romantic_confession", "date")
                    and is_check_success(a.get("check"), default_if_none=True)
                    for a in (actions or [])
                    if isinstance(a, dict)
                )
            )
            if track == "romantic" and existing_track != "romantic":
                # Let _evaluate_npc_milestones be the sole promoter from non-romantic -> romantic (enforcing D6 score >= 100)
                track = existing_track
            elif not track:
                track = existing_track
  
            app_dict = dict(contact.get("appearance", {})) if (contact and contact.get("appearance")) else {}
            new_mem = None
            
            # Tier 1 Structured Intimate Disclosure Processing
            revealed_attrs = rel.get("revealed_attributes", []) or []
            if isinstance(revealed_attrs, str):
                revealed_attrs = [revealed_attrs]
            revealed_set = {str(a).lower().strip() for a in revealed_attrs if a}
  
            if overall_check_success:
                if "sensitive_spots" in revealed_set or rel.get("sensitive_spots_revealed") or "turn_ons" in revealed_set or rel.get("turn_ons_revealed") or rel.get("turn_offs_revealed"):
                    app_dict["sensitive_spots_revealed"] = True
                    app_dict["turn_ons_revealed"] = True
                    app_dict["turn_offs_revealed"] = True
                if "fetishes" in revealed_set or rel.get("fetishes_revealed"):
                    app_dict["fetishes_revealed"] = True
                if "act_preferences" in revealed_set or rel.get("act_preferences_revealed") or "preferred_acts" in revealed_set:
                    app_dict["act_preferences_revealed"] = True
                if ("demeanor" in revealed_set or "intimate_demeanor" in revealed_set) or rel.get("demeanor_revealed"):
                    app_dict["demeanor_revealed"] = True
                if ("dynamic" in revealed_set or "intimate_dynamic" in revealed_set) or rel.get("dynamic_revealed"):
                    app_dict["dynamic_revealed"] = True
                if ("openness" in revealed_set or "erotic_openness" in revealed_set) or rel.get("openness_revealed"):
                    app_dict["openness_revealed"] = True
                if "intercourse" in revealed_set or rel.get("intercourse_revealed"):
                    app_dict["intercourse_revealed"] = True
                    app_dict["oral_revealed"] = True
                if "oral" in revealed_set or rel.get("oral_revealed"):
                    app_dict["oral_revealed"] = True
                if "manual" in revealed_set or rel.get("manual_revealed"):
                    app_dict["manual_revealed"] = True
                if "anal" in revealed_set or rel.get("anal_revealed"):
                    app_dict["anal_revealed"] = True
                if "all_intimate" in revealed_set or "intimate_profile" in revealed_set or intimate_rev:
                    app_dict["intimate_revealed"] = True
                    app_dict["sensitive_spots_revealed"] = True
                    app_dict["turn_ons_revealed"] = True
                    app_dict["fetishes_revealed"] = True
                    app_dict["act_preferences_revealed"] = True
                    app_dict["demeanor_revealed"] = True
                    app_dict["dynamic_revealed"] = True
                    app_dict["openness_revealed"] = True
                    app_dict["intercourse_revealed"] = True
                    app_dict["oral_revealed"] = True
                    app_dict["manual_revealed"] = True
                    app_dict["anal_revealed"] = True
  
            if rel.get("mannerisms_revealed"):
                app_dict["mannerisms_revealed"] = True
  
            # Custom intimate attribute strings if provided (strict validation; never overwrite established canon)
            from mechanics.social.persona import is_valid_persona_attribute_string
            if is_valid_persona_attribute_string(rel.get("new_sensitive_spots")):
                if not is_valid_persona_attribute_string(app_dict.get("sensitive_spots")):
                    app_dict["sensitive_spots"] = str(rel.get("new_sensitive_spots")).strip()
            if is_valid_persona_attribute_string(rel.get("new_turn_ons")):
                if not is_valid_persona_attribute_string(app_dict.get("turn_ons")):
                    app_dict["turn_ons"] = str(rel.get("new_turn_ons")).strip()
            if is_valid_persona_attribute_string(rel.get("new_fetishes")):
                if not is_valid_persona_attribute_string(app_dict.get("fetishes")):
                    app_dict["fetishes"] = str(rel.get("new_fetishes")).strip()
            if is_valid_persona_attribute_string(rel.get("new_act_likes")):
                if not is_valid_persona_attribute_string(app_dict.get("act_likes")):
                    app_dict["act_likes"] = str(rel.get("new_act_likes")).strip()
            if is_valid_persona_attribute_string(rel.get("new_act_dislikes")):
                if not is_valid_persona_attribute_string(app_dict.get("act_dislikes")):
                    app_dict["act_dislikes"] = str(rel.get("new_act_dislikes")).strip()
            if is_valid_persona_attribute_string(rel.get("new_demeanor")):
                if not is_valid_persona_attribute_string(app_dict.get("intimate_demeanor")):
                    app_dict["intimate_demeanor"] = str(rel.get("new_demeanor")).strip()
            if is_valid_persona_attribute_string(rel.get("new_dynamic")):
                if not is_valid_persona_attribute_string(app_dict.get("intimate_dynamic")):
                    app_dict["intimate_dynamic"] = str(rel.get("new_dynamic")).strip()
            if is_valid_persona_attribute_string(rel.get("new_openness")):
                if not is_valid_persona_attribute_string(app_dict.get("erotic_openness")):
                    app_dict["erotic_openness"] = str(rel.get("new_openness")).strip()
  
            if app_dict.get("intimate_revealed"):
                app_dict["intercourse_revealed"] = True
                app_dict["oral_revealed"] = True
                app_dict["manual_revealed"] = True
                app_dict["anal_revealed"] = True
                app_dict["demeanor_revealed"] = True
                app_dict["dynamic_revealed"] = True
                app_dict["openness_revealed"] = True
                app_dict["sensitive_spots_revealed"] = True
                app_dict["turn_ons_revealed"] = True
                app_dict["fetishes_revealed"] = True
                app_dict["act_preferences_revealed"] = True
  
            # Check player actions for successful intimate / personal inquiry targeting this NPC (no prose scraping)
            import namegen
            npc_toks = namegen.get_unique_person_tokens(npc_name, min_len=2) if npc_name else set()
            for a in actions:
                a_check = a.get("check")
                is_success = is_check_success(a_check, default_if_none=False)
  
                if is_success:
                    a_label = str(a.get("label", "")).lower()
                    a_tgt_low = str(a.get("target_npc") or "").lower().strip()
                    npc_mentioned = (
                        (npc_name.lower() in a_label)
                        or any(matches_keyword_boundary(a_label, tok) for tok in npc_toks if len(tok) >= 2)
                        or (a_tgt_low and (a_tgt_low == npc_name.lower() or a_tgt_low in npc_toks))
                        or (is_target_npc and not action_explicit_targets)
                    )
                    if npc_mentioned:
                        if any(kw in a_label for kw in ("sensitive spot", "erogenous", "touch where", "tickle", "turn on", "turn-on", "turns her on", "turns him on", "arousal trigger")):
                            app_dict["sensitive_spots_revealed"] = True
                            app_dict["turn_ons_revealed"] = True
                            rel["turn_ons_revealed"] = True
                        if any(kw in a_label for kw in ("fetish", "kink", "fantasy", "roleplay in bed", "bondage")):
                            app_dict["fetishes_revealed"] = True
                            rel["fetishes_revealed"] = True
                        if any(kw in a_label for kw in ("like in bed", "preferred position", "bedroom preference", "likes oral", "dislikes")):
                            app_dict["act_preferences_revealed"] = True
                            rel["act_preferences_revealed"] = True
                        if any(kw in a_label for kw in ("virgin", "virginity", "first time", "experienced", "past partner", "done oral", "received oral", "manual")):
                            app_dict["intercourse_revealed"] = True
                            app_dict["oral_revealed"] = True
                            app_dict["manual_revealed"] = True
                            rel["intercourse_revealed"] = True
                            rel["oral_revealed"] = True
                        if any(kw in a_label for kw in ("bedroom demeanor", "intimate demeanor", "in private", "in bed")):
                            app_dict["demeanor_revealed"] = True
                            rel["demeanor_revealed"] = True
                        if any(kw in a_label for kw in ("personal detail", "intimate detail", "intimate secret", "bedroom preference", "intimate preference", "ask about preference", "inquire about preference", "confess preference", "admit preference", "whisper preference")):
                            app_dict["intimate_revealed"] = True
                            app_dict["sensitive_spots_revealed"] = True
                            app_dict["turn_ons_revealed"] = True
                            app_dict["fetishes_revealed"] = True
                            app_dict["act_preferences_revealed"] = True
                            app_dict["demeanor_revealed"] = True
                            app_dict["intercourse_revealed"] = True
                            app_dict["oral_revealed"] = True
                            app_dict["manual_revealed"] = True
                            rel["intimate_revealed"] = True
                        if any(kw in a_label for kw in ("observe", "watch closely", "study expression", "study her expression", "study his expression", "notice body language", "watch body language", "scrutinize", "gauge reaction")):
                            app_dict["mannerisms_revealed"] = True
                            rel["mannerisms_revealed"] = True
  
            single_update = len(outcome.get("relationship_updates", [])) == 1
            raw_contact_score = int((contact or {}).get("relationship_score", 0) or 0)
            (
                new_mem,
                current_intercourse,
                current_oral,
                current_manual,
                track,
                is_intimate_act,
                delta_boost,
            ) = _evaluate_npc_milestones(
                npc_name=npc_name,
                app_dict=app_dict,
                track=track,
                milestone_ev=milestone_ev,
                custom_summary=custom_summary,
                intercourse_exp=intercourse_exp,
                oral_exp=oral_exp,
                actions=actions,
                narrative_text="",
                overall_check_success=overall_check_success,
                is_player_romantic_action=is_player_romantic_action,
                is_player_intimate_action=is_player_intimate_action,
                is_player_oral_action=is_player_oral_action,
                is_player_intercourse_action=is_player_intercourse_action,
                is_player_confession_action=is_player_confession_action,
                is_player_affection_action=is_player_affection_action,
                affection_target_npc=affection_target_npc,
                gift_target_npc=gift_target_npc,
                gift_item_name=gift_item_name,
                confession_target_npc=confession_target_npc,
                first_char_name=first_char_name,
                session=session,
                single_update=single_update,
                combined_check_text=combined_check_text,
                current_score=raw_contact_score,
            )
            confession_too_early = bool(app_dict.pop("_confession_too_early", False))
            resolved_milestone_ev = str(app_dict.pop("_resolved_milestone_event", "") or "").strip()
            if confession_too_early:
                delta = 2
                track = existing_track
                new_mem = None
                resolved_milestone_ev = ""
            elif delta_boost and delta == 0:
                delta = delta_boost

            # Strict romance track guard (D6): Only an explicit, successful romantic confession
            # or romantic date targeting this NPC with pre-turn score >= 100 can promote to romantic.
            if track == "romantic" and existing_track != "romantic":
                has_rom_promotion = (
                    (is_player_confession_action and is_confession_target_npc and overall_check_success)
                    or (resolved_milestone_ev in ("confession", "date") and overall_check_success)
                )
                if confession_too_early or not has_rom_promotion or raw_contact_score < 100:
                    track = existing_track
  
            app_dict["intercourse_experience"] = current_intercourse
            app_dict["oral_experience"] = current_oral
            app_dict["manual_experience"] = current_manual

            # Synchronize computed deterministic affinity delta with outcome object
            rel["delta_score"] = delta

            processed_npcs.add(npc_name.lower().strip())
            if contact and contact.get("name"):
                processed_npcs.add(contact["name"].lower().strip())
            import namegen
            npc_given_tok = namegen.get_given_name(npc_name).lower().strip() if npc_name else ""
            if npc_given_tok and len(npc_given_tok) >= 2 and npc_given_tok not in namegen.NAME_PARTICLES_AND_HONORIFICS:
                # Only add bare given name if no other contact shares it
                processed_npcs.add(f"__given__:{npc_given_tok}")
  
            rel_binfo = {}
            for k in ("role", "description", "faction", "club", "club_role", "grade", "race", "gender"):
                val = rel.get(k)
                if val not in (None, "", "None", "Unknown", [], {}):
                    rel_binfo[k] = val
  
            rel_race = rel.get("race", "")
            rel_gender = rel.get("gender", "")
            if not rel_race and contact and contact.get("race"):
                rel_race = contact.get("race")
            if not rel_gender and contact and contact.get("gender"):
                rel_gender = contact.get("gender")

            from mechanics.social.persona import is_romantic_milestone_str
            rom_mem = new_mem if (new_mem and is_romantic_milestone_str(new_mem)) else None
            gen_mem = new_mem if (new_mem and not is_romantic_milestone_str(new_mem)) else None
            if not gen_mem and custom_summary and not (rom_mem and rom_mem == custom_summary):
                if not is_romantic_milestone_str(custom_summary):
                    gen_mem = custom_summary.strip()
                elif not rom_mem and not confession_too_early:
                    rom_mem = custom_summary.strip()

            from mechanics.social.relationships import is_contact_eligible
            is_c_promoted_parent = bool(
                contact
                and (
                    contact.get("household_role") in ("father", "mother")
                    or (contact.get("basic_info") or {}).get("is_adult_family")
                )
            )
            if not is_c_promoted_parent and not is_contact_eligible(name=npc_name, role=rel_binfo.get("role", ""), description=rel_binfo.get("description", ""), scenario=scen_key, session_id=session_id):
                m_val = rel.get("mannerisms") or (app_dict.get("mannerisms") if isinstance(app_dict, dict) else "") or ""
                db.upsert_lorebook_entity(
                    session_id=session_id,
                    entity_type="person",
                    name=npc_name,
                    description=rel_binfo.get("description", ""),
                    traits=traits,
                    mannerisms=m_val,
                    race=rel_race,
                    appearance=app_dict if app_dict else {},
                    gender=rel_gender,
                )
                continue

            upserted = db.upsert_contact(
                session_id=session_id,
                character_id=first_char_id,
                npc_id=npc_name,
                name=npc_name,
                basic_info=rel_binfo if rel_binfo else None,
                delta_score=delta,
                track=track,
                new_traits=traits,
                new_preferences=prefs,
                race=rel_race,
                gender=rel_gender,
                appearance=app_dict if app_dict else None,
                new_memory=rom_mem,
                new_general_memory=gen_mem,
                narrative_text=narrative_text
            )
            turn_num = len((session or {}).get("history") or []) + 1
            cur_day_val = int((session or {}).get("current_day") or 1)
            cur_loc_val = str(outcome.get("location") or (session or {}).get("current_location") or "")

            if session_id and resolved_milestone_ev:
                try:
                    from mechanics.social.persona.intimacy.ledger import record_intimate_turn_encounter
                    u_dict = upserted if isinstance(upserted, dict) else {}
                    record_intimate_turn_encounter(
                        session_id=session_id,
                        character_id=str(u_dict.get("npc_id") or (contact or {}).get("npc_id") or npc_name),
                        character_name=str(u_dict.get("name") or npc_name),
                        character_gender=str(u_dict.get("gender") or rel_gender or "female"),
                        partner_id="player",
                        partner_name=first_char_name,
                        milestone_event=resolved_milestone_ev,
                        turn_number=turn_num,
                        day_number=cur_day_val,
                        location=cur_loc_val,
                        custom_summary=rom_mem or gen_mem or None,
                    )
                except Exception as _led_err:
                    log.warning("Failed to record intimate turn encounter for %s: %s", npc_name, _led_err)

            if session_id and track == "romantic" and existing_track != "romantic":
                try:
                    import mechanics.social.relationship_graph as rg
                    u_dict = upserted if isinstance(upserted, dict) else {}
                    c_npc_id = str(u_dict.get("npc_id") or (contact or {}).get("npc_id") or npc_name)
                    c_key = rg.canonical_person_key(c_npc_id)
                    cur_player_p = rg.get_current_partner(session_id, "player")
                    player_has_other_partner = bool(cur_player_p and cur_player_p.get("person_key") != c_key)
                    if not player_has_other_partner:
                        rg.end_tie(session_id, "player", c_key, rg.TIETYPE_AFFAIR, turn=turn_num, reason="promoted_to_dating", materialize=False)
                    rg.form_tie(
                        session_id,
                        "player",
                        c_key,
                        rg.TIETYPE_DATING,
                        closeness=80,
                        turn=turn_num,
                        origin="gameplay",
                        supersede=not player_has_other_partner,
                    )
                    rg.materialize_and_save_relations(session_id, c_npc_id)
                except Exception as _tie_err:
                    log.warning("Failed to form romantic tie for %s: %s", npc_name, _tie_err)
  
            updated_contact = db.get_contact(session_id, npc_name, first_char_id)
            # Breakup handling: If affinity plunges into negative territory (< 0), demote romantic track to platonic
            if updated_contact and str(updated_contact.get("track", "")).lower() == "romantic" and updated_contact.get("relationship_score", 0) < 0:
                db.update_contact_track(session_id, npc_name, "platonic", character_id=first_char_id)
                try:
                    import mechanics.social.relationship_graph as rg
                    npc_key = rg.canonical_person_key(updated_contact.get("npc_id") or npc_name)
                    rg.end_all_romantic_ties(session_id, "player", npc_key, turn=turn_num, reason="affinity_collapse")
                    c_npc_id = updated_contact.get("npc_id") or npc_name
                    rg.materialize_and_save_relations(session_id, c_npc_id)
                except Exception as e:
                    up_rels = updated_contact.get("relations") or {}
                    up_rels["romance"] = {"status": "Single", "current_partner": None}
                    db.update_contact_relations(session_id, npc_name, up_rels, character_id=first_char_id)

                db.upsert_contact(
                    session_id=session_id,
                    character_id=first_char_id,
                    npc_id=npc_name,
                    name=npc_name,
                    new_general_memory=f"{first_char_name} and {npc_name} broke up due to falling relationship affinity."
                )

            # Phase 2: Cross-Sibling Affinity & Milestone Ripples (Dual-Scope)
            sibling_name = None
            if "school" in scen_key:
                try:
                    s_roster = db.get_school_roster(session_id)
                    for s_ent in s_roster:
                        if s_ent.get("name", "").lower() == npc_name.lower() and s_ent.get("sibling_name"):
                            sibling_name = s_ent.get("sibling_name")
                            break
                except Exception:
                    pass

            if not sibling_name and contact:
                try:
                    import namegen
                    c_rels = contact.get("relations") or {}
                    for fam in c_rels.get("family", []):
                        rel_lbl_low = str(fam.get("relation", "")).lower()
                        if any(k in rel_lbl_low for k in ("brother", "sister", "sibling", "twin")):
                            sib_g = "female" if "sister" in rel_lbl_low else ("male" if "brother" in rel_lbl_low else "")
                            sibling_name = fam.get("name") or namegen.format_cultural_full_name(
                                str(fam.get("first_name", "")).strip(),
                                str(fam.get("surname", "")).strip(),
                                gender=sib_g,
                                deterministic_seed=f"sib_fallback_{npc_name}",
                            ).strip()
                            if sibling_name:
                                break
                except Exception:
                    pass

            if sibling_name and sibling_name.lower() != npc_name.lower():
                existing_sib_c = db.get_contact(session_id, sibling_name, first_char_id)
                sib_binfo = None if existing_sib_c else {"offscreen_ripple_only": True}
                # 1. Severe Hostility Ripple (delta <= -5 ripples as -2 protective friction)
                if delta <= -5:
                    db.update_relationship_score(session_id, sibling_name, -2, character_id=first_char_id)
                    db.upsert_contact(
                        session_id=session_id,
                        character_id=first_char_id,
                        npc_id=sibling_name,
                        name=sibling_name,
                        basic_info=sib_binfo,
                        new_general_memory=f"{first_char_name} was hostile towards my sibling {npc_name}."
                    )
                # 2. Romantic Milestone Ripple (accepted confession / dating awareness)
                elif track == "romantic" and existing_track != "romantic" and overall_check_success and delta > 0:
                    db.upsert_contact(
                        session_id=session_id,
                        character_id=first_char_id,
                        npc_id=sibling_name,
                        name=sibling_name,
                        basic_info=sib_binfo,
                        new_general_memory=f"Heard that {first_char_name} and {npc_name} started dating."
                    )
  
    # Automated Deterministic Milestone Scanner for active session contacts (strictly scoped to target NPC)
    if overall_check_success and (is_player_romantic_action or is_player_intimate_action or is_player_intercourse_action or is_player_oral_action):
        import namegen
        session_contacts = db.get_contacts(session_id, first_char_id)
        contact_peer_names = [sc.get("name", "") for sc in session_contacts if sc.get("name")]
        given_counts: dict[str, int] = {}
        for sc_nm in contact_peer_names:
            gv = namegen.get_given_name(sc_nm).lower().strip()
            if gv:
                given_counts[gv] = given_counts.get(gv, 0) + 1
        conf_toks = namegen.get_unique_person_tokens(confession_target_npc, peer_names=contact_peer_names, min_len=2) if confession_target_npc else set()
        for c in session_contacts:
            c_name = c.get("name", "")
            c_name_lower = c_name.lower().strip() if c_name else ""
            c_given = namegen.get_given_name(c_name).lower().strip() if c_name else ""
            c_toks = namegen.get_unique_person_tokens(c_name, peer_names=contact_peer_names, min_len=2) if c_name else set()
            
            is_processed = (c_name_lower in processed_npcs) or (
                bool(c_given) and given_counts.get(c_given, 0) == 1 and f"__given__:{c_given}" in processed_npcs
            )
            # Must be the explicit target of action or dialogue partner
            is_target = any(
                (
                    c_name_lower in str(a.get("label", "")).lower()
                    or any(matches_keyword_boundary(str(a.get("label", "")).lower(), tok) for tok in c_toks if len(tok) >= 2)
                    or str(a.get("target_npc") or "").lower().strip() == c_name_lower
                    or str(a.get("target_npc") or "").lower().strip() in c_toks
                )
                for a in actions
            ) or bool(session and game_engine.is_dialogue_partner(c_name, session=session)) or bool(
                confession_target_npc and (c_name_lower == confession_target_npc.lower().strip() or bool(c_toks & conf_toks))
            )
            
            if c_name and not is_processed and is_target:
                app_dict = dict(c.get("appearance", {}))
                orig_track = c.get("track", "platonic")
                orig_app = dict(app_dict)
                raw_c_score = int(c.get("relationship_score", 0) or 0)
  
                (
                    new_mem,
                    current_intercourse,
                    current_oral,
                    current_manual,
                    track,
                    is_intimate_act,
                    _delta_boost,
                ) = _evaluate_npc_milestones(
                    npc_name=c_name,
                    app_dict=app_dict,
                    track=orig_track,
                    milestone_ev="",
                    custom_summary=None,
                    intercourse_exp="",
                    oral_exp="",
                    actions=actions,
                    narrative_text="",
                    overall_check_success=overall_check_success,
                    is_player_romantic_action=is_player_romantic_action,
                    is_player_intimate_action=is_player_intimate_action,
                    is_player_oral_action=is_player_oral_action,
                    is_player_intercourse_action=is_player_intercourse_action,
                    is_player_confession_action=is_player_confession_action,
                    is_player_affection_action=is_player_affection_action,
                    affection_target_npc=affection_target_npc,
                    gift_target_npc=gift_target_npc,
                    gift_item_name=gift_item_name,
                    confession_target_npc=confession_target_npc,
                    first_char_name=first_char_name,
                    session=session,
                    single_update=False,
                    combined_check_text=combined_check_text,
                    current_score=raw_c_score,
                )

                is_conf_target = (
                    bool(confession_target_npc and (c_name_lower == confession_target_npc.lower().strip() or bool(c_toks & conf_toks)))
                    or any(
                        (is_romantic_confession_intent(str(a.get("label", ""))) or a.get("intent") == "romantic_confession")
                        and (
                            c_name_lower in str(a.get("label", "")).lower()
                            or any(matches_keyword_boundary(str(a.get("label", "")).lower(), tok) for tok in c_toks if len(tok) >= 2)
                        )
                        for a in (actions or [])
                    )
                    or (not confession_target_npc and is_target)
                )

                scan_confession_early = bool(app_dict.pop("_confession_too_early", False))
                resolved_scan_ev = str(app_dict.pop("_resolved_milestone_event", "") or "").strip()
                scan_delta = 2 if scan_confession_early else 0
                if scan_confession_early:
                    track = orig_track
                    new_mem = None
                    resolved_scan_ev = ""

                if track == "romantic" and orig_track != "romantic":
                    has_rom_scan = (
                        (is_player_confession_action and is_conf_target and overall_check_success)
                        or (resolved_scan_ev in ("confession", "date") and overall_check_success)
                    )
                    if scan_confession_early or not has_rom_scan or raw_c_score < 100:
                        track = orig_track
  
                app_dict["intercourse_experience"] = current_intercourse
                app_dict["oral_experience"] = current_oral
                app_dict["manual_experience"] = current_manual
  
                changed = bool(new_mem) or (track != orig_track) or (app_dict != orig_app) or bool(resolved_scan_ev) or scan_delta != 0
  
                if changed:
                    from mechanics.social.persona import is_romantic_milestone_str
                    rom_mem = new_mem if (new_mem and is_romantic_milestone_str(new_mem)) else None
                    gen_mem = new_mem if (new_mem and not is_romantic_milestone_str(new_mem)) else None
                    upserted_scan = db.upsert_contact(
                        session_id=session_id,
                        character_id=first_char_id,
                        npc_id=c_name,
                        name=c_name,
                        delta_score=scan_delta,
                        track=track,
                        appearance=app_dict,
                        new_memory=rom_mem,
                        new_general_memory=gen_mem,
                    )
                    turn_num_scan = len((session or {}).get("history") or []) + 1
                    if session_id and resolved_scan_ev:
                        try:
                            from mechanics.social.persona.intimacy.ledger import record_intimate_turn_encounter
                            u_sc = upserted_scan if isinstance(upserted_scan, dict) else {}
                            record_intimate_turn_encounter(
                                session_id=session_id,
                                character_id=str(u_sc.get("npc_id") or c.get("npc_id") or c_name),
                                character_name=str(u_sc.get("name") or c_name),
                                character_gender=str(u_sc.get("gender") or c.get("gender") or "female"),
                                partner_id="player",
                                partner_name=first_char_name,
                                milestone_event=resolved_scan_ev,
                                turn_number=turn_num_scan,
                                day_number=int((session or {}).get("current_day") or 1),
                                location=str(outcome.get("location") or (session or {}).get("current_location") or ""),
                                custom_summary=rom_mem or gen_mem or None,
                            )
                        except Exception as _led_err2:
                            log.warning("Failed to record scanned intimate encounter for %s: %s", c_name, _led_err2)
                    if session_id and track == "romantic" and orig_track != "romantic":
                        try:
                            import mechanics.social.relationship_graph as rg
                            c_npc_id = str((upserted_scan or {}).get("npc_id") or c.get("npc_id") or c_name)
                            rg.form_tie(
                                session_id,
                                "player",
                                rg.canonical_person_key(c_npc_id),
                                rg.TIETYPE_DATING,
                                closeness=80,
                                turn=turn_num_scan,
                                origin="gameplay",
                                supersede=False,
                            )
                            rg.materialize_and_save_relations(session_id, c_npc_id)
                        except Exception:
                            pass

    # Phase 2.4 (A2): Immediate Secret Affair Discovery when Primary Partner is Co-Located
    if session_id and present_npc_names:
        try:
            import mechanics.social.relationship_graph as rg
            primary_partner = rg.get_current_partner(session_id, "player")
            if primary_partner:
                prim_key = str(primary_partner.get("person_key") or "")
                prim_disp = str(primary_partner.get("display_name") or prim_key.replace("_", " ").title()).strip()
                prim_npc_id = rg.resolve_npc_id_for_person(session_id, prim_key) or prim_disp
                prim_in_scene = (
                    prim_disp.lower() in present_npc_names
                    or prim_key.replace("_", " ") in present_npc_names
                    or prim_npc_id.lower().replace("_", " ") in present_npc_names
                )
                if prim_in_scene:
                    affair_ties = rg.get_secret_affairs(session_id, "player") or []
                    caught_affair_name = ""
                    # Check 1: Active secret affair partner co-located during intimate/romantic action
                    if is_player_romantic_action or is_player_intimate_action or is_player_intercourse_action or is_player_oral_action:
                        for af in affair_ties:
                            af_key = str(af.get("person_key") or "")
                            af_disp = str(af.get("display_name") or af_key.replace("_", " ").title()).strip()
                            if af_key != prim_key and (
                                af_disp.lower() in present_npc_names
                                or af_key.replace("_", " ") in present_npc_names
                            ):
                                caught_affair_name = af_disp
                                break
                    # Check 2: Intimate ledger event recorded this turn with someone other than primary partner
                    if not caught_affair_name:
                        turn_num_now = len((session or {}).get("history") or []) + 1
                        with db.get_conn() as _conn:
                            cheat_row = _conn.execute(
                                """SELECT character_id FROM intimate_events
                                   WHERE session_id = ? AND turn_number = ? AND event_origin = 'gameplay'
                                     AND partner_id = 'player'
                                     AND act_type IN ('intercourse', 'oral', 'manual', 'anal', 'kiss', 'confession', 'date')""",
                                (session_id, turn_num_now),
                            ).fetchone()
                        if cheat_row:
                            ch_key = rg.canonical_person_key(cheat_row["character_id"])
                            if ch_key and ch_key != prim_key:
                                ch_person = rg.get_person(session_id, ch_key)
                                caught_affair_name = str((ch_person or {}).get("display_name") or ch_key.replace("_", " ").title())

                    if caught_affair_name:
                        turn_num_now = len((session or {}).get("history") or []) + 1
                        db.update_relationship_score(session_id, prim_npc_id, -40, character_id=first_char_id)
                        db.update_contact_track(session_id, prim_npc_id, "platonic", character_id=first_char_id)
                        rg.end_all_romantic_ties(session_id, "player", prim_key, turn=turn_num_now, reason="caught_cheating")
                        rg.materialize_and_save_relations(session_id, prim_npc_id)
                        db.upsert_contact(
                            session_id=session_id,
                            character_id=first_char_id,
                            npc_id=prim_npc_id,
                            name=prim_disp,
                            track="platonic",
                            new_general_memory=f"Caught {first_char_name} cheating in person with {caught_affair_name} and angrily ended their relationship.",
                        )
                        notices = outcome.setdefault("system_notices", [])
                        if isinstance(notices, list):
                            notices.append(f"💔 {prim_disp} caught {first_char_name} with {caught_affair_name}! (-40 Affinity, Relationship Ended)")
        except Exception as _affair_err:
            log.warning("Immediate affair discovery check failed: %s", _affair_err)


from .reducers import _evaluate_npc_milestones
from .core import get_combined_narrative, is_check_success


def resolve_pre_turn_social_and_disclosures(
    session: Dict[str, Any],
    party: Optional[List[Any]] = None,
    actions: Optional[List[Any]] = None,
    new_dialogue_partners: Optional[List[str]] = None,
    persist_db: bool = True,
) -> Dict[str, Any]:
    """
    Deterministic pre-turn social affinity, canonical disclosure, and witness resolution engine.
    Runs BEFORE the Narrator LLM on social/dialogue turns:
    1. Evaluates active dialogue partners across all co-op actions and computes deterministic affinity deltas.
    2. Enforces D6 (< 100 Confession/Date Gate) with +2 flattered platonic affinity and stage direction.
    3. Checks successful disclosure inquiries and PER observations (staged when persist_db=False for D3).
    4. Evaluates witness detection and queues 0ms procedural gossip feed posts.
    """
    import db
    from skill_check import is_check_success
    from mechanics.social.affinity_engine import calculate_social_affinity_delta
    from mechanics.social.relationships import is_romantic_confession_intent
    from mechanics.system.phone.social_graph import evaluate_pre_turn_witness_detection
    from mechanics.world.mobility import get_session_dialogue_partners

    session_id = session.get("id") or 0
    player_char = session.get("player_character")
    if not player_char and party:
        first_entry = party[0]
        player_char = first_entry[0] if isinstance(first_entry, (tuple, list)) else first_entry
    if not isinstance(player_char, dict):
        player_char = {}

    player_name = str(player_char.get("name") or "Player").strip()
    first_char_id = player_char.get("id") or player_char.get("user_id") or 1

    norm_actions: List[Dict[str, Any]] = [
        (a if isinstance(a, dict) else {"label": str(a)})
        for a in (actions or [])
        if a is not None
    ]
    first_action = norm_actions[0] if norm_actions else {}
    act_label = str(first_action.get("label") or first_action.get("action") or "")
    act_low = act_label.lower()
    is_success = is_check_success(first_action.get("check"), default_if_none=True)
    combined_act_low = " ".join(str(a.get("label") or a.get("action") or "").lower() for a in norm_actions)

    sess_dps = list(get_session_dialogue_partners(session))
    if new_dialogue_partners:
        for ndp in new_dialogue_partners:
            if ndp and ndp not in sess_dps:
                sess_dps.append(ndp)
    if not sess_dps and session.get("dialogue_partner"):
        sess_dps.append(session["dialogue_partner"])

    for a_item in norm_actions:
        act_tgt = str(a_item.get("target_npc") or "").strip()
        if act_tgt and act_tgt not in sess_dps:
            sess_dps.append(act_tgt)

    if not sess_dps and combined_act_low:
        c_npcs = session.get("current_npcs") or []
        if isinstance(c_npcs, list):
            for cn in c_npcs:
                n_name = cn.get("name") if isinstance(cn, dict) else str(cn)
                if n_name and len(n_name) >= 3 and n_name.lower() in combined_act_low and n_name not in sess_dps:
                    sess_dps.append(n_name)

    primary_target = sess_dps[0] if sess_dps else ""

    affinity_deltas: Dict[str, int] = {}
    directives: List[str] = []
    revealed_attributes: List[str] = []
    disclosed_appearances: List[Dict[str, Any]] = []
    staged_commitment_ops: List[Dict[str, Any]] = []

    # Check whether any co-op action explicitly addresses or targets specific NPC(s) (D15)
    from game_engine.matching import matches_keyword_boundary
    import namegen
    explicit_action_targets = set()
    for a_item in norm_actions:
        a_tgt = str(a_item.get("target_npc") or a_item.get("combat_target") or "").lower().strip()
        if a_tgt:
            explicit_action_targets.add(a_tgt)
        a_lbl_low = str(a_item.get("label") or a_item.get("action") or "").lower()
        for dp in sess_dps:
            dp_low = dp.lower().strip()
            dp_toks = namegen.get_unique_person_tokens(dp, peer_names=sess_dps, min_len=2)
            if matches_keyword_boundary(a_lbl_low, dp_low) or any(matches_keyword_boundary(a_lbl_low, tok) for tok in dp_toks if len(tok) >= 2):
                explicit_action_targets.add(dp_low)

    for npc_name in sess_dps:
        scen_str_soc = str(session.get("scenario") or "fantasy")
        try:
            from mechanics.narrative.intent import classify_action_intent, IntentCategory
            from mechanics.social.relationships import get_scenario_recruitment_phrasing
            for a_chk in norm_actions:
                lbl_chk = str(a_chk.get("label") or a_chk.get("action") or "")
                cls_chk = classify_action_intent(lbl_chk)
                is_rec_attempt = (
                    a_chk.get("intent") == "party_recruit"
                    or cls_chk.category == IntentCategory.PARTY_RECRUIT
                    or any(
                        k in lbl_chk.lower()
                        for k in (
                            "join my party", "join your party", "join our party", "join the party",
                            "permanent companion", "recruit into", "come fight with me", "join my squad",
                            "join your field team", "join your retinue", "travel with your retinue",
                            "travel with your group", "run with your team", "join your crew",
                            "partner up and join", "team up and join", "team up and travel",
                        )
                    )
                )
                if is_rec_attempt:
                    rec_phr = get_scenario_recruitment_phrasing(scen_str_soc, npc_name=npc_name, player_name=player_name)
                    if scenario_data.is_anomalous_incursions_scenario(scen_str_soc):
                        from mechanics.social.anomalous_npc_tags import classify_anomalous_npc_tag, TAG_CIVILIAN
                        c_ent = next(
                            (n for n in (session.get("current_npcs") or []) if isinstance(n, dict) and str(n.get("name") or "").strip().lower() == npc_name.lower()),
                            {"name": npc_name},
                        )
                        if classify_anomalous_npc_tag(c_ent, session_id=session_id, scen_key=scen_str_soc) == TAG_CIVILIAN:
                            directives.append(
                                f"[STAGE DIRECTION — CIVILIAN RECRUITMENT BLOCKED]: {npc_name} is an unawakened Civilian with zero mana reserves and no barrier training. "
                                f"They must decline joining {player_name}'s active field team (explaining naturally in-character that entering anomalous zones without mana would get an ordinary civilian killed), though they remain friendly/willing to stay in touch as a personal Contact."
                            )
                            break
                    directives.append(
                        f"[STAGE DIRECTION — NATURAL TEAM-UP / RECRUITMENT DIALOGUE ({npc_name})]: "
                        f"{player_name} is asking {npc_name} to team up and join their {rec_phr['group_noun']}. "
                        f"{rec_phr['narration_guidance']}"
                    )
                    break
        except Exception:
            pass
        contact = None
        if session_id:
            try:
                contact = db.get_contact(session_id, npc_name, first_char_id)
            except Exception:
                contact = None
        if not contact:
            contact = {
                "name": npc_name,
                "npc_id": npc_name.lower().replace(" ", "_"),
                "appearance": {},
                "relationship_score": 0,
            }

        n_low = npc_name.lower().strip()
        n_toks = namegen.get_unique_person_tokens(npc_name, peer_names=sess_dps, min_len=2)
        if explicit_action_targets:
            is_target = bool(
                n_low in explicit_action_targets
                or bool(n_toks & explicit_action_targets)
            )
        else:
            is_target = True

        npc_action = first_action
        for a_item in norm_actions:
            a_tgt = str(a_item.get("target_npc") or a_item.get("combat_target") or "").lower().strip()
            a_lbl_low = str(a_item.get("label") or a_item.get("action") or "").lower()
            if (
                a_tgt == n_low
                or a_tgt in n_toks
                or matches_keyword_boundary(a_lbl_low, n_low)
                or any(matches_keyword_boundary(a_lbl_low, tok) for tok in n_toks if len(tok) >= 2)
            ):
                npc_action = a_item
                break

        npc_act_label = str(npc_action.get("label") or npc_action.get("action") or "")
        npc_act_low = npc_act_label.lower()
        npc_act_success = is_check_success(npc_action.get("check"), default_if_none=True)

        # Deterministic affinity delta calculation
        from mechanics.social.conversation_choices import (
            resolve_partner_conversation_profile as _pre_res_prof,
            get_partner_conversation_budget_state as _pre_get_bstate,
            is_non_quest_social_turn_action as _pre_is_nq_social,
        )
        _pre_prof = _pre_res_prof(session, npc_name, party=party)
        _pre_bstate = _pre_get_bstate(session, _pre_prof)
        _npc_eval_act = dict(npc_action)
        if _pre_prof.get("is_private_meetup"):
            _npc_eval_act["is_private_meetup"] = True
        _imp_b, _imp_r = _resolve_player_social_impression_bonus(session, party)
        delta, reasons, breakdown = calculate_social_affinity_delta(
            action=_npc_eval_act,
            npc_name=npc_name,
            contact_data=contact,
            is_target_npc=is_target,
            social_impression_bonus=_imp_b,
            social_impression_reason=_imp_r,
        )
        _pre_intent_low = str(npc_action.get("intent") or "").lower().strip()
        if (
            is_target
            and int(_pre_bstate.get("remaining_budget", 3)) <= 0
            and _pre_is_nq_social(npc_action, was_already_partner=True)
            and _pre_intent_low not in ("romantic_confession", "phone_contact_exchange", "gift_offer", "intimate_act")
        ):
            npc_action["_post_budget_zero_affinity"] = True
            if delta > 0:
                delta = 0
            directives.append(
                f"[STAGE DIRECTION — CONVERSATION WRAPPING UP]: {npc_name} replies politely and briefly while naturally signaling they need to get back to what they were doing."
            )

        # D6: Score < 100 Confession / Romantic Date Gate
        npc_intent = str(npc_action.get("intent") or "").lower().strip()
        npc_sub = str(npc_action.get("sub_intent") or "").lower().strip()
        is_rom_gate_act = (
            npc_intent == "romantic_confession"
            or npc_sub in ("confession", "date")
            or is_romantic_confession_intent(npc_act_label)
        )
        c_track = str(contact.get("track") or "platonic").strip().lower()
        c_score = int(contact.get("relationship_score", contact.get("score", 0)) or 0)
        if is_target and npc_act_success and is_rom_gate_act and c_track != "romantic" and c_score < 100:
            delta = 2
            directives.append(
                f"[STAGE DIRECTION — CONFESSION TOO EARLY]: {npc_name} is genuinely flattered by {player_name}'s romantic feelings (+2 platonic affinity), gently explains they aren't ready to start dating yet, and remains on the platonic track."
            )

        affinity_deltas[npc_name] = delta

        # Disclosure inquiry checks if action succeeded
        if npc_act_success and npc_act_label and is_target:
            app_dict = dict(contact.get("appearance") or {})
            a_tgt_cur = str(npc_action.get("target_npc") or "").lower().strip()
            npc_mentioned = (
                (npc_name.lower() in npc_act_low)
                or any(matches_keyword_boundary(npc_act_low, tok) for tok in n_toks if len(tok) >= 2)
                or (a_tgt_cur and (a_tgt_cur == n_low or a_tgt_cur in n_toks))
                or (not explicit_action_targets and npc_name == primary_target)
            )

            if npc_mentioned:
                revealed_for_npc = []
                if any(kw in npc_act_low for kw in ("sensitive spot", "erogenous", "touch where", "tickle", "turn on", "turn-on", "turns her on", "turns him on", "arousal trigger")):
                    app_dict["sensitive_spots_revealed"] = True
                    app_dict["turn_ons_revealed"] = True
                    revealed_for_npc.extend(["sensitive_spots", "turn_ons"])
                if any(kw in npc_act_low for kw in ("fetish", "kink", "fantasy", "roleplay in bed", "bondage")):
                    app_dict["fetishes_revealed"] = True
                    revealed_for_npc.append("fetishes")
                if any(kw in npc_act_low for kw in ("like in bed", "preferred position", "bedroom preference", "likes oral", "dislikes")):
                    app_dict["act_preferences_revealed"] = True
                    revealed_for_npc.append("act_preferences")
                if any(kw in npc_act_low for kw in ("virgin", "virginity", "first time", "experienced", "past partner", "done oral", "received oral", "manual")):
                    app_dict["intercourse_revealed"] = True
                    app_dict["oral_revealed"] = True
                    app_dict["manual_revealed"] = True
                    revealed_for_npc.extend(["intercourse_experience", "oral_experience"])
                if any(kw in npc_act_low for kw in ("bedroom demeanor", "intimate demeanor", "in private", "in bed")):
                    app_dict["demeanor_revealed"] = True
                    revealed_for_npc.append("intimate_demeanor")
                if any(kw in npc_act_low for kw in ("observe", "watch closely", "study expression", "study her expression", "study his expression", "notice body language", "watch body language", "scrutinize", "gauge reaction")):
                    app_dict["mannerisms_revealed"] = True
                    revealed_for_npc.append("mannerisms")
                if any(kw in npc_act_low for kw in ("personal detail", "intimate detail", "intimate secret", "bedroom preference", "intimate preference", "ask about preference", "inquire about preference", "confess preference", "admit preference", "whisper preference")):
                    app_dict["intimate_revealed"] = True
                    app_dict["sensitive_spots_revealed"] = True
                    app_dict["turn_ons_revealed"] = True
                    app_dict["fetishes_revealed"] = True
                    app_dict["act_preferences_revealed"] = True
                    app_dict["demeanor_revealed"] = True
                    app_dict["intercourse_revealed"] = True
                    app_dict["oral_revealed"] = True
                    app_dict["manual_revealed"] = True
                    revealed_for_npc.extend(["sensitive_spots", "turn_ons", "fetishes", "intimate_demeanor"])

                if revealed_for_npc:
                    revealed_attributes.extend(revealed_for_npc)
                    scen_key = str(session.get("scenario") or "fantasy")
                    if any(rk != "mannerisms" for rk in revealed_for_npc):
                        app_dict["intimate_revealed"] = True
                    if any(not app_dict.get(rk) for rk in revealed_for_npc):
                        try:
                            from mechanics.social.persona import normalize_appearance
                            app_dict = normalize_appearance(
                                app_dict,
                                gender=str(contact.get("gender") or ""),
                                race=str(contact.get("race") or "human"),
                                desc=npc_name,
                                scen_key=scen_key,
                                traits=contact.get("unlocked_traits") or [],
                                role=str((contact.get("basic_info") or {}).get("role") or ""),
                            )
                        except Exception:
                            pass
                    if session_id:
                        c_id = contact.get("npc_id") or npc_name.lower().replace(" ", "_")
                        if persist_db:
                            try:
                                db.upsert_contact(
                                    session_id=session_id,
                                    npc_id=c_id,
                                    name=npc_name,
                                    character_id=first_char_id,
                                    delta_score=0,
                                    appearance=app_dict,
                                )
                                db.upsert_contact(
                                    session_id=session_id,
                                    npc_id=c_id,
                                    name=npc_name,
                                    character_id=0,
                                    delta_score=0,
                                    appearance=app_dict,
                                )
                            except Exception:
                                pass
                        else:
                            disclosed_appearances.append({
                                "npc_id": c_id,
                                "name": npc_name,
                                "appearance": dict(app_dict),
                            })

                    # Format mandatory disclosure directives
                    for r_key in set(revealed_for_npc):
                        r_val = app_dict.get(r_key)
                        if r_val:
                            clean_val = str(r_val).strip()
                            clean_tag = r_key.replace("_", " ")
                            directives.append(
                                f"[MANDATORY CANONICAL DISCLOSURE]: {npc_name} reveals their canonical {clean_tag}: '{clean_val}'. Weave this exact truth into their dialogue/reaction."
                            )

    # Deterministic commitment fulfillment, breakage & immediate creation resolution (Hybrid A3)
    fulfilled_commitments: list[int] = []
    broken_commitments: list[int] = []
    created_commitments: list[dict] = []
    if session_id and combined_act_low:
        try:
            import json as _json
            from db.memory import get_active_commitments, add_commitment
            from mechanics.system.commitments_engine import fulfill_commitment, flake_commitment, create_rendezvous
            active_commits = get_active_commitments(session_id) or []
            _fulfill_kws = ("fulfill", "keep promise", "kept promise", "repay", "pay back", "deliver", "hand over", "return the", "honor pact")
            _break_kws = ("break promise", "broke promise", "betray", "refuse to pay", "expose secret", "spill secret", "tell secret", "renounce pact")
            is_unverified_custom = bool(first_action.get("is_custom") or first_action.get("source") == "custom")
            turn_num_pre = len(session.get("history") or []) + 1
            player_uid_pre = int(player_char.get("user_id") or session.get("host_user_id") or 0)
            player_gold_pre = int(player_char.get("gold") or 0)
            player_inv_names: set[str] | None = None

            c_scene_npcs = session.get("current_npcs") or []
            present_names = [
                (n.get("name") if isinstance(n, dict) else str(n)).strip()
                for n in c_scene_npcs
                if (isinstance(n, dict) and n.get("name")) or (isinstance(n, str) and n.strip())
            ]
            target_npcs = [str(p).strip() for p in sess_dps if p]

            for cm in active_commits:
                cid = cm.get("id")
                if not cid or str(cm.get("commitment_type") or "") == "rendezvous":
                    continue
                c_src = str(cm.get("source_entity") or "").strip().lower()
                c_tgt = str(cm.get("target_entity") or "").strip().lower()
                c_desc = str(cm.get("description") or "").strip()
                c_npc_raw = c_tgt if c_src in ("player", player_name.lower(), player_name.lower().replace(" ", "_"), "") else c_src
                c_npc = c_npc_raw.replace("_", " ").strip()
                c_npc_first = (c_npc.split() or [""])[0]
                npc_in_scene = any(
                    c_npc == tn.lower().replace("_", " ").strip()
                    or (len(c_npc_first) >= 3 and c_npc_first == (tn.lower().replace("_", " ").split() or [""])[0])
                    for tn in (target_npcs + present_names)
                )
                if not npc_in_scene and c_npc and c_npc not in combined_act_low and (len(c_npc_first) < 3 or c_npc_first not in combined_act_low):
                    continue

                raw_meta = cm.get("metadata_json") or cm.get("metadata") or "{}"
                try:
                    cm_meta = _json.loads(raw_meta) if isinstance(raw_meta, str) else (raw_meta or {})
                except Exception:
                    cm_meta = {}
                req_gold = int(cm_meta.get("gold_amount") or 0)
                req_item = str(cm_meta.get("item_name") or "").strip().lower()

                if is_success and any(kw in combined_act_low for kw in _fulfill_kws):
                    can_fulfill_pre = True
                    deduct_gold_for_cm = 0
                    if req_gold > 0:
                        if player_gold_pre < req_gold:
                            can_fulfill_pre = False
                            directives.append(
                                f"[COMMITMENT UNFULFILLED — INSUFFICIENT GOLD]: {player_name} attempted to repay '{c_desc}', but only has {player_gold_pre}g (requires {req_gold}g)."
                            )
                        elif player_uid_pre:
                            player_gold_pre -= req_gold
                            player_char["gold"] = player_gold_pre
                            deduct_gold_for_cm = req_gold
                            if persist_db:
                                db.update_character_fields(player_uid_pre, gold=player_gold_pre)
                    elif req_item:
                        if player_inv_names is None:
                            inv_rows = db.get_inventory(player_uid_pre) if player_uid_pre else []
                            player_inv_names = {str(it.get("item_name") or it.get("name") or "").strip().lower() for it in (inv_rows or [])}
                        if not any(req_item in iname or iname in req_item for iname in player_inv_names if iname):
                            can_fulfill_pre = False
                            directives.append(
                                f"[COMMITMENT UNFULFILLED — MISSING ITEM]: {player_name} attempted to fulfill '{c_desc}', but does not possess '{cm_meta.get('item_name')}'."
                            )
                    elif is_unverified_custom:
                        can_fulfill_pre = False
                        directives.append(
                            f"[ACTIVE COMMITMENT VERIFICATION]: Active commitment #{cid} ('{c_desc}') with {c_npc.title() or 'the NPC'}. Include {cid} in fulfilled_commitments ONLY if genuinely completed in this scene."
                        )

                    if can_fulfill_pre:
                        if persist_db:
                            fulfill_commitment(session_id, int(cid), current_turn=turn_num_pre)
                        else:
                            staged_commitment_ops.append({
                                "op": "fulfill",
                                "cid": int(cid),
                                "turn": turn_num_pre,
                                "gold_deduct_uid": player_uid_pre if deduct_gold_for_cm > 0 else 0,
                                "gold_deduct_amount": deduct_gold_for_cm,
                            })
                        fulfilled_commitments.append(int(cid))
                        directives.append(
                            f"[MANDATORY COMMITMENT FULFILLED]: The commitment '{c_desc}' with {c_npc.title() or 'the NPC'} has been fulfilled! Acknowledge this in the narrative."
                        )
                elif any(kw in combined_act_low for kw in _break_kws) and not is_unverified_custom:
                    if persist_db:
                        flake_commitment(session_id, int(cid), reason="broken promise", current_turn=turn_num_pre)
                    else:
                        staged_commitment_ops.append({
                            "op": "flake",
                            "cid": int(cid),
                            "reason": "broken promise",
                            "turn": turn_num_pre,
                        })
                    broken_commitments.append(int(cid))
                    directives.append(
                        f"[MANDATORY COMMITMENT BROKEN]: The commitment '{c_desc}' with {c_npc.title() or 'the NPC'} has been broken! Reflect their reaction in the narrative."
                    )

            # Immediate Pre-Turn Commitment Creation (Promises, Pacts, Debts, Secrets, and In-Person Rendezvous)
            if is_success and not fulfilled_commitments and not broken_commitments:
                commit_partner = primary_target or (present_names[0] if present_names else "")
                _meet_m = re.search(
                    r"\b(?:meet(?:\s+up)?(?:\s+with\s+[a-z'\-]+)?|rendezvous|hang\s+out|go\s+on\s+a\s+date)\b.*?\bat\s+(?:the\s+)?([A-Z][A-Za-z0-9 '\-➔]{2,45})",
                    act_label,
                )
                if _meet_m and commit_partner and not is_unverified_custom:
                    meet_loc = _meet_m.group(1).strip().rstrip(".,!?")
                    cur_d, cur_m, _ = db.get_session_time(session_id)
                    start_m = min(1380, ((cur_m + 60) // 15) * 15)
                    end_m = (start_m + 120) % 1440
                    end_d = cur_d + 1 if end_m < start_m else cur_d
                    rv_kwargs = {
                        "session_id": session_id,
                        "participants": [commit_partner],
                        "location": meet_loc,
                        "day": cur_d,
                        "start_minute": start_m,
                        "end_minute": end_m,
                        "end_day": end_d,
                        "purpose": "date" if "date" in act_low else "hangout",
                        "is_confidential": ("secret" in act_low or "private" in act_low),
                        "source_channel": "in_person",
                        "current_turn": turn_num_pre,
                    }
                    if persist_db:
                        rv_res = create_rendezvous(**rv_kwargs)
                        if rv_res and rv_res.get("commitment_id"):
                            created_commitments.append(rv_res)
                            directives.append(
                                f"[MANDATORY RENDEZVOUS SCHEDULED]: {player_name} and {commit_partner} agreed in person to meet at '{meet_loc}'."
                            )
                    else:
                        staged_commitment_ops.append({"op": "create_rendezvous", "kwargs": rv_kwargs})
                        created_commitments.append({"location": meet_loc, "participants": [commit_partner], "_staged": True})
                        directives.append(
                            f"[MANDATORY RENDEZVOUS SCHEDULED]: {player_name} and {commit_partner} agreed in person to meet at '{meet_loc}'."
                        )
                else:
                    _create_map = [
                        ("pact", ("swear a pact", "forge a pact", "make a pact", "seal a pact", "blood oath")),
                        ("secret", ("swear secrecy", "keep secret", "keep her secret", "keep his secret", "keep their secret", "never tell anyone")),
                        ("debt", ("owe you", "promise to repay", "borrow gold", "in your debt")),
                        ("promise", ("promise to", "i promise", "swear to", "vow to", "give my word", "agree to help")),
                    ]
                    matched_ctype = None
                    for ctype, kws in _create_map:
                        if any(kw in act_low for kw in kws):
                            matched_ctype = ctype
                            break
                    if matched_ctype and commit_partner:
                        clean_desc = act_label.strip().rstrip(".")
                        already_exists = any(
                            str(cm.get("target_entity") or "").strip().lower() == commit_partner.lower()
                            and str(cm.get("description") or "").strip().lower() == clean_desc.lower()
                            for cm in active_commits
                        )
                        if not already_exists:
                            turn_num = len(session.get("history") or [])
                            cm_kwargs = {
                                "session_id": session_id,
                                "source_entity": "player",
                                "target_entity": commit_partner,
                                "commitment_type": matched_ctype,
                                "description": clean_desc,
                                "turn_number": turn_num,
                            }
                            if persist_db:
                                new_cm = add_commitment(**cm_kwargs)
                                if new_cm:
                                    created_commitments.append(new_cm)
                                    directives.append(
                                        f"[MANDATORY NEW COMMITMENT RECORDED]: {player_name} made a binding {matched_ctype} with {commit_partner}: '{clean_desc}'. Have {commit_partner} acknowledge this pledge."
                                    )
                            else:
                                staged_commitment_ops.append({"op": "add_commitment", "kwargs": cm_kwargs})
                                created_commitments.append({**cm_kwargs, "_staged": True})
                                directives.append(
                                    f"[MANDATORY NEW COMMITMENT RECORDED]: {player_name} made a binding {matched_ctype} with {commit_partner}: '{clean_desc}'. Have {commit_partner} acknowledge this pledge."
                                )
        except Exception as e:
            log.warning("Commitment resolution error: %s", e)

    # Deterministic Pre-Turn Faction Discovery, Endorsements, Direct Faction Actions & Promotion Trials
    faction_updates: list[dict] = []
    faction_promotion_result: str = ""
    if session_id:
        try:
            # 1. Resolve Pending Faction Promotion Trial deterministically from skill check
            pending_promo = session.get("pending_promotion")
            if isinstance(pending_promo, dict) and pending_promo.get("faction_id"):
                from mechanics.combat import is_in_combat
                is_setup_turn = (
                    "initiates promotion trial" in act_low
                    or "faction promotion trial directive" in act_low
                )
                has_trial_check = (
                    first_action.get("check") is not None
                    or str(first_action.get("stat") or "NONE").upper() not in ("NONE", "FREE", "")
                )
                if not is_setup_turn and has_trial_check and not is_in_combat(session):
                    p_fid = str(pending_promo.get("faction_id") or "").strip()
                    p_rank = int(pending_promo.get("target_rank") or 1)
                    p_tmpl = str(pending_promo.get("template") or "guild")
                    from mechanics.social.factions import get_rank_title
                    p_title = get_rank_title(p_tmpl, p_rank)
                    if is_success:
                        faction_promotion_result = "success"
                        directives.append(
                            f"[MANDATORY FACTION PROMOTION COMPLETE]: {player_name} succeeded in the promotion trial for '{p_fid}' and has been promoted to Rank {p_rank} ({p_title})! Narrate the formal recognition and promotion ceremony."
                        )
                    else:
                        faction_promotion_result = "failed"
                        directives.append(
                            f"[FACTION PROMOTION TRIAL FAILED]: {player_name} fell short in the promotion trial for '{p_fid}' (Rank {p_rank}: {p_title}). Narrate why the trial was not passed yet."
                        )

            # 2. Deterministic Faction Discovery & Milestone Endorsements from Contact Interactions
            for npc_name, aff_delta in affinity_deltas.items():
                c_row = db.get_contact(session_id, npc_name, first_char_id) or db.get_contact(session_id, npc_name.lower().replace(" ", "_"))
                if not c_row:
                    continue
                b_info = c_row.get("basic_info") or {}
                c_fac = str(
                    b_info.get("faction")
                    or b_info.get("faction_affiliation")
                    or b_info.get("club")
                    or c_row.get("faction")
                    or ""
                ).strip()
                if not c_fac or c_fac.lower() in ("none", "unaligned", ""):
                    continue
                old_sc = int(c_row.get("relationship_score", c_row.get("score", 0)) or 0)
                new_sc = old_sc + int(aff_delta or 0)
                existing_fac_row = db.get_faction(session_id, c_fac)

                if old_sc < 30 and new_sc >= 30:
                    faction_updates.append({
                        "faction_name": c_fac,
                        "delta_score": 5,
                        "notes": f"Milestone endorsement from {npc_name} (Reached Friend status).",
                        "_pre_turn_resolved": True,
                    })
                    directives.append(
                        f"[STAGE DIRECTION — FACTION ENDORSEMENT]: Reaching Friend status with {npc_name} earned +5 Reputation with '{c_fac}'."
                    )
                elif aff_delta <= -5:
                    faction_updates.append({
                        "faction_name": c_fac,
                        "delta_score": -2,
                        "notes": f"Friction with affiliated member {npc_name}.",
                        "_pre_turn_resolved": True,
                    })
                elif not existing_fac_row:
                    faction_updates.append({
                        "faction_name": c_fac,
                        "delta_score": 0,
                        "notes": f"Introduced via {npc_name}.",
                        "_pre_turn_resolved": True,
                    })

            # 3. Direct Non-Contact Faction Actions (Supportive +3 / Hostile Sabotage -5)
            if combined_act_low:
                known_factions = db.get_factions(session_id) or []
                already_updated_fnames = {str(f.get("faction_name") or "").lower() for f in faction_updates}
                _fac_support_kws = ("help ", "assist ", "defend ", "protect ", "support ", "reinforce ", "aid ", "donate ", "deliver to ", "rescue ")
                _fac_hostile_kws = ("sabotage ", "attack ", "raid ", "steal from ", "rob ", "ambush ", "destroy ", "vandalize ", "betray ", "infiltrate ", "disrupt ")
                for kf in known_factions:
                    kf_name = str(kf.get("name") or "").strip()
                    if not kf_name or kf_name.lower() in already_updated_fnames:
                        continue
                    if kf_name.lower() in combined_act_low:
                        if any(kw in combined_act_low for kw in _fac_hostile_kws):
                            faction_updates.append({
                                "faction_name": kf_name,
                                "delta_score": -5,
                                "notes": f"Direct hostile action against {kf_name}: {act_label[:80]}",
                                "_pre_turn_resolved": True,
                            })
                            already_updated_fnames.add(kf_name.lower())
                            directives.append(
                                f"[STAGE DIRECTION — FACTION HOSTILITY]: {player_name}'s action against '{kf_name}' incurred -5 Reputation."
                            )
                        elif is_success and any(kw in combined_act_low for kw in _fac_support_kws):
                            faction_updates.append({
                                "faction_name": kf_name,
                                "delta_score": 3,
                                "notes": f"Direct support for {kf_name}: {act_label[:80]}",
                                "_pre_turn_resolved": True,
                            })
                            already_updated_fnames.add(kf_name.lower())
                            directives.append(
                                f"[STAGE DIRECTION — FACTION SUPPORT]: {player_name}'s assistance earned +3 Reputation with '{kf_name}'."
                            )
        except Exception as e:
            log.warning("Pre-turn faction resolution error: %s", e)

    # Deterministic witness detection
    witness_res = evaluate_pre_turn_witness_detection(
        session=session,
        actions=actions or [],
        player_name=player_name,
        target_npc=primary_target,
        location_str=session.get("current_location", ""),
    )
    if witness_res.get("witness_spotted") and witness_res.get("directive"):
        directives.append(witness_res["directive"])

    res = {
        "affinity_deltas": affinity_deltas,
        "revealed_attributes": revealed_attributes,
        "disclosed_appearances": disclosed_appearances,
        "staged_commitment_ops": staged_commitment_ops,
        "fulfilled_commitments": fulfilled_commitments,
        "broken_commitments": broken_commitments,
        "created_commitments": created_commitments,
        "faction_updates": faction_updates,
        "faction_promotion_result": faction_promotion_result,
        "directives": directives,
        "witness_detection": witness_res,
    }
    session["_pre_turn_social_res"] = res
    return res

