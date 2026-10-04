from .constants import *
import mechanics.narrative.event_handlers
from mechanics.narrative.events import bus, LocationChangedEvent, NPCSpawnedEvent, NPCStatusChangedEvent, ItemGiftedEvent, ItemGainedEvent, FactionLeadershipChangedEvent, QuestCompletedEvent
import json
import re
import logging
import game_engine

log = logging.getLogger(__name__)

def _reduce_social_and_milestones(session_id: int, session: dict, party: list, outcome: dict, actions: list, scen_key: str, items_gained_by_user: dict, first_char_id: int, first_char_name: str):
    """Extracted Phase 2B Reducer for Relationships, Milestones, and Escorts."""
    import db, game_engine, json, re
    from game_engine.core import PLAYER_ROMANTIC_ACTION_KEYWORDS, PLAYER_INTIMATE_ACTION_KEYWORDS, PLAYER_ORAL_ACTION_KEYWORDS, PLAYER_INTERCOURSE_ACTION_KEYWORDS
      # Narrative text for automated milestone scanning
    narrative_text = (str(outcome.get("outcome_narrative", "")) + " " + str(outcome.get("next_narrative", "")) + " " + str(outcome.get("narrative", ""))).lower()
    
    # Decrement recruitment and confession cooldowns for session
    db.decrement_recruitment_cooldowns(session_id)
    db.decrement_confession_cooldowns(session_id)
  
    # Process Party Companion / Social Escort Recruitment & Dismissal
    from scenario_data import is_mechanic_enabled
    from mechanics.narrative.intent import classify_action_intent, IntentCategory
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
  
    for a in (actions or []):
        a_label = str(a.get("label", ""))
        a_parsed = classify_action_intent(a_label)
        is_recruit = (
            (is_combat_scen and a_parsed.category == IntentCategory.PARTY_RECRUIT)
            or (not is_combat_scen and a_parsed.category in (IntentCategory.PARTY_RECRUIT, IntentCategory.SOCIAL_INVITE))
        )
        if is_recruit:
            a_check = a.get("check")
            is_success = is_check_success(a_check, default_if_none=not is_combat_scen)
  
            # Identify target NPC from label or dialogue_partners or current_npcs
            target_npc_name = None
            curr_npcs = session.get("current_npcs", []) if session else []
            for npc in curr_npcs:
                n_name = game_engine._get_npc_name(npc)
                if n_name and n_name.lower() != "none" and (n_name.lower() in a_label.lower() or (a_parsed.target_entity and n_name.lower() == a_parsed.target_entity.lower())):
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
                if is_success:
                    party_npcs = db.get_session_party_npcs(session_id)
                    human_count = len(session.get("turn_order", [])) if session else 1
                    if human_count + len(party_npcs) < 4:
                        party_level = max(1, party[0][0].get("level", 1)) if (party and party[0]) else 1
                        comp_hp = 15 + party_level * 3 if is_combat_scen else 100
                        comp_mp = 10 + party_level * 2 if is_combat_scen else 100
                        from mechanics.world.locations import resolve_companion_origin_location
                        origin_loc = resolve_companion_origin_location(session_id, session.get("current_location", "") if session else "", scen_key)
                        
                        lore_ent = next((p for p in db.get_lorebook(session_id).get("person", []) if p.get("name", "").lower() == target_npc_name.lower()), {})
                        role_desc = lore_ent.get("description", "Companion") or "Companion"
                        role_clean = "Companion"
                        if is_combat_scen:
                            for cand in ["Scout", "Warrior", "Mage", "Cleric", "Rogue", "Paladin", "Archer", "Guard", "Scholar", "Alchemist", "Knight", "Assassin", "Mercenary"]:
                                if cand.lower() in role_desc.lower() or cand.lower() in target_npc_name.lower():
                                    role_clean = cand
                                    break
                        else:
                            contact_c = db.get_contact(session_id, target_npc_name.lower().replace(" ", "_"))
                            c_trk = str(contact_c.get("track") or "").lower() if contact_c else ""
                            c_sc = contact_c.get("relationship_score", 0) if contact_c else 0
                            if "date" in a_label or c_trk == "romance" or c_sc >= 15:
                                role_clean = "Date"
                            elif "study" in a_label:
                                role_clean = "Study Partner"
                            else:
                                role_clean = "Friend"
                            
                        companion_data = {
                            "name": target_npc_name,
                            "role": role_clean,
                            "level": party_level,
                            "hp": comp_hp,
                            "max_hp": comp_hp,
                            "mp": comp_mp,
                            "max_mp": comp_mp,
                            "status_effects": [],
                            "origin_location": origin_loc,
                            "race": lore_ent.get("race") or "",
                            "appearance": lore_ent.get("appearance_json", {})
                        }
                        db.add_session_party_npc(session_id, companion_data)
                        
                        new_curr_npcs = [n for n in curr_npcs if (n.get("name", "") if isinstance(n, dict) else str(n)).lower() != target_npc_name.lower()]
                        db.update_session_npcs(session_id, new_curr_npcs)
                        
                        db.upsert_contact(
                            session_id=session_id,
                            character_id=first_char_id,
                            npc_id=target_npc_name,
                            name=target_npc_name,
                            delta_score=5,
                            track="platonic"
                        )
                else:
                    db.set_recruitment_cooldown(session_id, target_npc_name, turns=3)
  
    # Auto-register all non-hostile scene NPCs into contacts
    if is_mechanic_enabled(scen_key, "contact_list") or is_mechanic_enabled(scen_key, "relationship_meter"):
        enemy_list = game_engine.get_active_enemies(outcome) or game_engine.get_active_enemies(session)
        enemy_names = {game_engine._get_npc_name(e).lower() for e in enemy_list if e}
        party_names = {str(c[0]["name"]).strip().lower() for c in party if c and c[0] and c[0].get("name")}
        
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
            from namegen import is_generic_role_name
            disp = str(npc.get("disposition", "")).lower() if isinstance(npc, dict) else ""
            is_dialogue = game_engine.is_dialogue_partner(n_name, active_partners) or game_engine.is_dialogue_partner(n_name, [str(a.get("label", "")) for a in (actions or [])])
            if is_generic_role_name(n_name) and not is_dialogue and disp not in ("friendly", "companion", "ally"):
                continue
  
            n_role = (npc.get("role") if isinstance(npc, dict) else "") or ""
            n_desc = (npc.get("description") if isinstance(npc, dict) else "") or ""
  
            # Check Peer / Role Eligibility (e.g. students vs teachers/parents/clerks in high school)
            import mechanics.social.relationships as relationships
            if not relationships.is_contact_eligible(name=n_name, role=n_role, description=n_desc, scenario=scen_key):
                continue
  
            n_traits = (npc.get("traits") if isinstance(npc, dict) else []) or []
            n_prefs = (npc.get("preferences") if isinstance(npc, dict) else []) or []
            n_race = (npc.get("race") if isinstance(npc, dict) else "") or ""
            n_gender = (npc.get("gender") if isinstance(npc, dict) else "") or ""
            n_app = (npc.get("appearance") if isinstance(npc, dict) else {}) or {}
            
            basic_info = {}
            if isinstance(npc, dict):
                for k in ("role", "occupation", "description", "faction", "club", "club_role", "grade", "clique", "age", "location", "mannerisms", "motivation", "disposition"):
                    val = npc.get(k)
                    if val not in (None, "", "None", "Unknown", [], {}):
                        basic_info[k] = val
                
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
  
            from mechanics.narrative.intent import is_conversational_exit
            is_exit = is_conversational_exit(label_low)
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
                if not any(game_engine.is_dialogue_partner(t_npc, [ru_name]) for ru_name in existing_ru_names):
                    if stat in ("CHA", "INT", "PER", "STR", "AGI", "END"):
                        if tier in ("crit_success", "critical_success"):
                            fb_delta = 4
                        elif tier in ("success", "partial_success"):
                            fb_delta = 3
                        elif tier in ("fail", "failure"):
                            fb_delta = -1
                        elif tier in ("crit_fail", "critical_failure"):
                            fb_delta = -3
                        else:
                            fb_delta = 2
                    else:
                        fb_delta = 1
  
                    if "relationship_updates" not in outcome or not isinstance(outcome["relationship_updates"], list):
                        outcome["relationship_updates"] = []
                    outcome["relationship_updates"].append({
                        "npc_name": t_npc,
                        "delta_score": fb_delta,
                        "track": "platonic"
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
    for rel in (outcome.get("relationship_updates") or []):
        if not isinstance(rel, dict):
            continue
        r_name = rel.get("npc_name") or rel.get("name") or ""
        if not is_valid_entity_name(r_name):
            continue
            
        if enforce_perspective and r_name.lower() not in present_npc_names:
            log.warning(f"Perspective Filter triggered: Dropping relationship update for {r_name} because they were not present in the scene.")
            continue
            
        r_role = rel.get("role", "")
        r_desc = rel.get("description", "")
        if not r_role or not r_desc:
            for npc in (all_scene_npcs or []):
                if isinstance(npc, dict) and str(npc.get("name", "")).strip().lower() == str(r_name).strip().lower():
                    r_role = r_role or npc.get("role", "")
                    r_desc = r_desc or npc.get("description", "")
                    break
        if r_name and not relationships.is_contact_eligible(name=r_name, role=r_role, description=r_desc, scenario=scen_key, session_id=session_id):
            continue
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
        parsed_a = classify_action_intent(a_lbl, ctx_a)
  
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
        if parsed_a.category == IntentCategory.GIFT_OFFER:
            gift_target_npc = a.get("target_npc") or parsed_a.target_entity or _primary_dp
            gift_item_name = parsed_a.sub_target or parsed_a.metadata.get("item_name", "Gift")
  
        # Check Intimate Act intent
        if parsed_a.category == IntentCategory.INTIMATE_ACT:
            if chk_ok:
                is_player_intimate_action = True
                if parsed_a.sub_target == "intercourse":
                    is_player_intercourse_action = True
                elif parsed_a.sub_target in ("oral_give", "oral_receive"):
                    is_player_oral_action = True
  
        if chk_ok:
            if any(kw in a_lbl.lower() for kw in PLAYER_ROMANTIC_ACTION_KEYWORDS) or is_conf:
                is_player_romantic_action = True
            if any(kw in a_lbl.lower() for kw in PLAYER_INTIMATE_ACTION_KEYWORDS):
                is_player_intimate_action = True
            is_oral_act = any(kw in a_lbl.lower() for kw in PLAYER_ORAL_ACTION_KEYWORDS) or (parsed_a and parsed_a.sub_target in ("oral_give", "oral_receive"))
            if is_oral_act:
                is_player_oral_action = True
                is_player_intimate_action = True
            has_explicit_penetration = any(kw in a_lbl.lower() for kw in ("dick", "cock", "shaft", "penis", "have sex", "make love", "penetrate", "fuck", "creampie", "breed"))
            if any(kw in a_lbl.lower() for kw in PLAYER_INTERCOURSE_ACTION_KEYWORDS):
                if not is_oral_act or has_explicit_penetration:
                    is_player_intercourse_action = True
  
    # Process explicit relationship updates from LLM outcome
    narrative_text = get_combined_narrative(outcome)
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
            n_low = npc_name.lower().strip()
            n_first = (n_low.split() or [""])[0]

            # Determine whether npc_name is an active participant / target of the player's action
            is_target_npc = (
                any(
                    (n_low in str(a.get("label", "")).lower() or (len(n_first) >= 3 and n_first in str(a.get("label", "")).lower()))
                    or (str(a.get("target_npc", "")).lower().strip() in (n_low, n_first))
                    for a in (actions or [])
                )
                or bool(session and game_engine.is_dialogue_partner(npc_name, session=session))
                or (confession_target_npc and (n_low == confession_target_npc.lower().strip() or n_first == (confession_target_npc.lower().split() or [""])[0]))
                or (affection_target_npc and (n_low == affection_target_npc.lower().strip() or n_first == (affection_target_npc.lower().split() or [""])[0]))
                or (gift_target_npc and (n_low == gift_target_npc.lower().strip() or n_first == (gift_target_npc.lower().split() or [""])[0]))
            )

            # Determine whether player's action towards this NPC was hostile
            hostile_keywords = (
                "attack", "punch", "strike", "slap", "shove", "kick", "stab", "shoot",
                "insult", "mock", "belittle", "humiliate", "threaten", "intimidate",
                "steal", "rob", "pickpocket", "poison", "betray"
            )
            is_hostile_action = any(
                any(kw in str(a.get("label", "")).lower() for kw in hostile_keywords)
                for a in (actions or [])
                if (n_low in str(a.get("label", "")).lower() or (len(n_first) >= 3 and n_first in str(a.get("label", "")).lower()))
            )

            # Find matching action for check evaluation
            primary_action = None
            for a in (actions or []):
                if n_low in str(a.get("label", "")).lower() or (len(n_first) >= 3 and n_first in str(a.get("label", "")).lower()) or str(a.get("target_npc", "")).lower().strip() in (n_low, n_first):
                    primary_action = a
                    break
            if not primary_action and actions:
                primary_action = actions[0]

            from mechanics.social.relationships import reconcile_action_affinity_delta, safe_clamp_delta
            delta = reconcile_action_affinity_delta(
                raw_delta=rel.get("delta_score", 0),
                action=primary_action,
                is_target=is_target_npc,
                overall_check_success=overall_check_success,
                is_hostile=is_hostile_action
            )
            traits = rel.get("new_traits", []) or []
            prefs = rel.get("new_preferences", []) or []
            track = rel.get("track", "")
            intercourse_exp = rel.get("intercourse_experience", "")
            oral_exp = rel.get("oral_experience", "")
            intimate_rev = rel.get("intimate_revealed", False)
            milestone_ev = str(rel.get("milestone_event", "")).lower().strip()
            custom_summary = rel.get("memory_summary") or rel.get("new_memory") or rel.get("memory")
  
            contact = db.get_contact(session_id, npc_name, first_char_id)
            c_traits = []
            c_prefs = []
            if contact:
                c_traits = contact.get("unlocked_traits") or contact.get("traits") or []
                c_prefs = contact.get("preferences") or []
            if not c_traits or not c_prefs:
                for npc in (all_scene_npcs or []):
                    if isinstance(npc, dict) and str(npc.get("name", "")).strip().lower() == npc_name.lower():
                        if not c_traits:
                            c_traits = npc.get("traits") or []
                        if not c_prefs:
                            c_prefs = npc.get("preferences") or []
                        break
            if not c_traits and rel.get("new_traits"):
                c_traits = rel.get("new_traits") or []
            if not c_prefs and rel.get("new_preferences"):
                c_prefs = rel.get("new_preferences") or []

            from mechanics.combat.traits import evaluate_trait_and_preference_impact
            act_label = " ".join(str(a.get("label", "")) for a in (actions or []) if isinstance(a, dict))
            if gift_item_name and gift_item_name.lower() not in act_label.lower():
                act_label = f"{act_label} {gift_item_name}".strip()
            delta, _notes = evaluate_trait_and_preference_impact(act_label, c_traits, c_prefs, base_delta=delta)
            if _notes:
                log.info("Trait/Preference affinity impact for %s: %s (delta: %s)", npc_name, ", ".join(_notes), delta)

            app_data = dict(contact.get("appearance", {})) if (contact and contact.get("appearance")) else {}
            if not app_data:
                for npc in (all_scene_npcs or []):
                    if isinstance(npc, dict) and str(npc.get("name", "")).strip().lower() == npc_name.lower():
                        if isinstance(npc.get("appearance"), dict):
                            app_data = dict(npc["appearance"])
                        break
            if isinstance(app_data, dict) and app_data:
                    op_val = str(app_data.get("erotic_openness") or app_data.get("openness") or "").lower()
                    is_intimate_act = any(k in act_label.lower() for k in ("intimate", "kiss", "undress", "touch", "suggestive", "flirt", "seduce", "bed", "naked", "strip", "embrace", "oral", "manual", "handjob", "fingering", "thrust", "intercourse"))
                    if is_intimate_act and op_val:
                        if "prude" in op_val or "modest" in op_val:
                            if overall_check_success is False or delta < 0:
                                delta -= 3
                            else:
                                delta = min(delta, 2)
                        elif "shameless" in op_val or "lewd" in op_val:
                            if overall_check_success and delta > 0:
                                delta += 2
                            elif delta < 0:
                                delta = max(delta, -1)
                        elif "bold" in op_val or "uninhibited" in op_val:
                            if overall_check_success and delta > 0:
                                delta += 1
  
                    # Turn-ons impact on delta (+2 bonus on success, -2 penalty on fail)
                    turn_ons = str(app_data.get("turn_ons") or app_data.get("sensitive_spots") or "").lower()
                    if turn_ons and turn_ons not in ("none", "unknown"):
                        triggers = [t.replace("(physical)", "").replace("(action)", "").strip() for t in turn_ons.split(",") if t.strip()]
                        for trig in triggers:
                            if not trig or len(trig) < 4:
                                continue
                            sig_words = [w for w in trig.split() if len(w) >= 4]
                            if trig in act_label.lower() or (len(sig_words) >= 2 and all(w in act_label.lower() for w in sig_words)):
                                if overall_check_success:
                                    delta += 2
                                else:
                                    delta -= 2
                                break
  
                    # Liked & Disliked Acts impact on delta
                    from mechanics.social.persona import ACT_PREFERENCE_REGISTRY
                    act_likes = str(app_data.get("act_likes") or "").lower()
                    act_dislikes = str(app_data.get("act_dislikes") or "").lower()
                    for pref_item in ACT_PREFERENCE_REGISTRY:
                        if any(kw in act_label.lower() for kw in pref_item["keywords"]):
                            p_name = pref_item["name"].lower()
                            p_id = pref_item["id"]
                            if p_name in act_likes or p_id in act_likes:
                                if overall_check_success:
                                    delta += 2
                            if p_name in act_dislikes or p_id in act_dislikes:
                                if overall_check_success:
                                    delta -= 1
                                else:
                                    delta -= 2
  
            has_explicit_check = bool(primary_action and primary_action.get("check"))
            if has_explicit_check and overall_check_success and not is_hostile_action and is_target_npc:
                delta = max(1, delta)
            elif not is_target_npc:
                delta = max(0, delta)
            delta = safe_clamp_delta(delta, min_val=-10, max_val=10)
  
            app_dict = dict(contact.get("appearance", {})) if (contact and contact.get("appearance")) else {}
            new_mem = None
            
            # Tier 1 Structured Intimate Disclosure Processing
            revealed_attrs = rel.get("revealed_attributes", []) or []
            if isinstance(revealed_attrs, str):
                revealed_attrs = [revealed_attrs]
            revealed_set = {str(a).lower().strip() for a in revealed_attrs if a}
  
            if overall_check_success:
                if "sensitive_spots" in revealed_set or rel.get("sensitive_spots_revealed") or "turn_ons" in revealed_set or rel.get("turn_ons_revealed"):
                    app_dict["sensitive_spots_revealed"] = True
                    app_dict["turn_ons_revealed"] = True
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
                    app_dict["intercourse_revealed"] = True
                if "oral" in revealed_set or rel.get("oral_revealed"):
                    app_dict["oral_revealed"] = True
                if "manual" in revealed_set or rel.get("manual_revealed"):
                    app_dict["manual_revealed"] = True
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
                    app_dict["intercourse_revealed"] = True
                    app_dict["oral_revealed"] = True
                    app_dict["manual_revealed"] = True
  
            if rel.get("mannerisms_revealed"):
                app_dict["mannerisms_revealed"] = True
  
            # Custom intimate attribute strings if provided (strict validation; never overwrite established canon)
            from mechanics.social.persona import is_valid_persona_attribute_string
            if is_valid_persona_attribute_string(rel.get("new_sensitive_spots")) or is_valid_persona_attribute_string(rel.get("new_turn_ons")):
                if not is_valid_persona_attribute_string(app_dict.get("turn_ons")):
                    t_val = str(rel.get("new_turn_ons") or rel.get("new_sensitive_spots")).strip()
                    app_dict["turn_ons"] = t_val
                    app_dict["sensitive_spots"] = t_val
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
                app_dict["demeanor_revealed"] = True
                app_dict["dynamic_revealed"] = True
                app_dict["openness_revealed"] = True
                app_dict["sensitive_spots_revealed"] = True
                app_dict["turn_ons_revealed"] = True
                app_dict["fetishes_revealed"] = True
                app_dict["act_preferences_revealed"] = True
  
            # Check player actions for successful intimate / personal inquiry targeting this NPC
            for a in actions:
                a_check = a.get("check")
                is_success = is_check_success(a_check, default_if_none=False)
  
                if is_success:
                    a_label = str(a.get("label", "")).lower()
                    n_lower = narrative_text.lower()
                    npc_first = npc_name.split()[0].lower() if npc_name else ""
                    npc_mentioned = (npc_name.lower() in a_label) or (npc_name.lower() in n_lower) or (len(npc_first) >= 3 and npc_first in a_label) or (len(npc_first) >= 3 and npc_first in n_lower)
                    if npc_mentioned:
                        if any(kw in a_label for kw in ("sensitive spot", "erogenous", "touch where", "tickle", "turn on", "turn-on", "turns her on", "turns him on", "arousal trigger")) or any(kw in n_lower for kw in ("sensitive spot", "erogenous zone", "turn on", "turn-on")):
                            app_dict["sensitive_spots_revealed"] = True
                            app_dict["turn_ons_revealed"] = True
                            rel["turn_ons_revealed"] = True
                        if any(kw in a_label for kw in ("fetish", "kink", "fantasy", "roleplay in bed", "bondage")) or any(kw in n_lower for kw in ("fetish", "kink", "unusual desire")):
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
                        if any(kw in a_label for kw in ("personal detail", "intimate detail", "intimate secret", "bedroom preference", "intimate preference", "ask about preference", "inquire about preference", "confess preference", "admit preference", "whisper preference")) or any(kw in n_lower for kw in ("admits her preference", "admits his preference", "admits their preference", "shared her secret preference", "shared his secret preference", "confessed her preference", "confessed his preference")):
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
                        if any(kw in a_label for kw in ("observe", "watch closely", "study expression", "study her expression", "study his expression", "notice body language", "watch body language", "scrutinize", "gauge reaction")) or any(kw in n_lower for kw in ("notices a subtle habit", "observes the subtle habit", "notices their mannerism")):
                            app_dict["mannerisms_revealed"] = True
                            rel["mannerisms_revealed"] = True
  
            single_update = len(outcome.get("relationship_updates", [])) == 1
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
                narrative_text=narrative_text,
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
            )
            if delta_boost and delta == 0:
                delta = delta_boost
  
            app_dict["intercourse_experience"] = current_intercourse
            app_dict["oral_experience"] = current_oral
            app_dict["manual_experience"] = current_manual

            # Synchronize computed deterministic affinity delta with outcome object
            rel["delta_score"] = delta

            processed_npcs.add(npc_name.lower().strip())
            if contact and contact.get("name"):
                processed_npcs.add(contact["name"].lower().strip())
            npc_first_token = npc_name.split()[0].lower().strip() if npc_name else ""
            if npc_first_token:
                processed_npcs.add(npc_first_token)
  
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

            db.upsert_contact(
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
                new_memory=new_mem,
                narrative_text=narrative_text
            )
  
            # Auto-promote neutral NPC to friendly in lorebook when positive affinity is established
            updated_contact = db.get_contact(session_id, npc_name, first_char_id)
            if updated_contact and (updated_contact.get("relationship_score", 0) >= 3 or delta > 0):
                up_binfo = updated_contact.get("basic_info") or {}
                db.upsert_lorebook_entity(
                    session_id=session_id,
                    entity_type="person",
                    name=updated_contact.get("name") or npc_name,
                    description=up_binfo.get("description", ""),
                    disposition="friendly",
                    faction=up_binfo.get("faction") or up_binfo.get("club") or "",
                    traits=updated_contact.get("unlocked_traits", []),
                    motivation=up_binfo.get("motivation", ""),
                    mannerisms=up_binfo.get("mannerisms", ""),
                    race=updated_contact.get("race") or "",
                    appearance=updated_contact.get("appearance", {})
                )
  
    # Automated Narrative Milestone Scanner for active session contacts (strictly scoped to target NPC)
    if overall_check_success and (is_player_romantic_action or is_player_intimate_action or is_player_intercourse_action or is_player_oral_action):
        session_contacts = db.get_contacts(session_id, first_char_id)
        for c in session_contacts:
            c_name = c.get("name", "")
            c_name_lower = c_name.lower().strip() if c_name else ""
            c_first = c_name_lower.split()[0] if c_name_lower else ""
            
            is_processed = (c_name_lower in processed_npcs) or (c_first in processed_npcs)
            # Must be the explicit target of action or dialogue partner
            is_target = any(
                (c_name_lower in str(a.get("label", "")).lower() or (len(c_first) >= 3 and c_first in str(a.get("label", "")).lower()))
                for a in actions
            ) or bool(session and game_engine.is_dialogue_partner(c_name, session=session)) or (confession_target_npc and (c_name_lower == confession_target_npc.lower().strip() or c_first == (confession_target_npc.lower().split() or [""])[0]))
            
            if c_name and not is_processed and is_target:
                app_dict = dict(c.get("appearance", {}))
                orig_track = c.get("track", "platonic")
                orig_app = dict(app_dict)
  
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
                    narrative_text=narrative_text,
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
                )
  
                app_dict["intercourse_experience"] = current_intercourse
                app_dict["oral_experience"] = current_oral
                app_dict["manual_experience"] = current_manual
  
                changed = bool(new_mem) or (track != orig_track) or (app_dict != orig_app)
  
                if changed:
                    db.upsert_contact(
                        session_id=session_id,
                        character_id=first_char_id,
                        npc_id=c_name,
                        name=c_name,
                        track=track,
                        appearance=app_dict,
                        new_memory=new_mem
                    )


from .reducers import _evaluate_npc_milestones
from .core import get_combined_narrative, is_check_success
