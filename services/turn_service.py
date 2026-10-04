import json
import logging
import asyncio
from typing import Dict, List, Any, Optional
from pydantic import BaseModel, ConfigDict
import db
from db import adb
import game_engine
from character_data import XP_REWARDS
from mechanics.combat.merchant import apply_merchant_encounter_result

log = logging.getLogger(__name__)


class TurnResponse(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    success: bool
    session: Dict[str, Any]
    outcome: Dict[str, Any]          # Always a dict — outcome is coerced before storing here
    action: Dict[str, Any]
    items_gained_by_user: Dict[Any, List[str]]   # {user_id: [item_name, ...]}
    xp_gained: int
    levels_gained: List[int]
    new_char: Dict[str, Any]


class TurnService:
    @staticmethod
    async def resolve_action(session_id: int, user_id: int, action: Dict[str, Any], mode: str = "solo", stream_callback=None) -> TurnResponse:
        """
        Unifies the turn resolution process across Discord and Web API using non-blocking DB access.
        """
        session = await adb(db.get_session, session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        members = await adb(db.get_session_members, session_id)
        party = []
        for uid in members:
            c = await adb(db.get_character, uid)
            if c:
                inv = await adb(db.get_inventory, uid)
                party.append((dict(c), inv))

        if mode == "sync" and len(party) > 1:
            picks = session.get("pending_picks", {})
            picks[str(user_id)] = action
            await adb(db.update_session, session_id, pending_picks_json=json.dumps(picks, default=str))

            if len(picks) < len(party):
                raise ValueError("waiting_for_party")

            # Everyone locked in
            actions = list(picks.values())
            mp_already_spent = {a.get("user_id", user_id): a.get("mp_spent", 0) for a in actions}
            await adb(db.update_session, session_id, pending_picks_json="{}")
        else:
            actions = [action]
            mp_already_spent = {user_id: action.get("mp_spent", 0)}

        # Serialize action helper
        def _serialize_action(a):
            c = a.get("check")
            check_dict = None
            if c:
                check_dict = {
                    "chance": getattr(c, "chance", a.get("rate")),
                    "roll": getattr(c, "roll", None),
                    "tier": getattr(c, "tier", a.get("tier", "fail")),
                    "tier_label": getattr(c, "tier_label", "Action"),
                    "succeeded": getattr(c, "succeeded", False)
                }
            return {
                "user_id": a.get("user_id", a.get("char", {}).get("user_id", 0)),
                "label": a.get("label", ""),
                "stat": a.get("stat", ""),
                "requirement": getattr(c, "requirement", a.get("requirement", 0)),
                "mp_spent": a.get("mp_spent", 0),
                "check": check_dict,
                "item_name": a.get("item_name"),
                "target_name": a.get("target_name"),
                "spell_id": a.get("spell_id"),
                "quest_id": a.get("quest_id"),
                "sub_obj_id": a.get("sub_obj_id"),
                "stage_index": a.get("stage_index"),
                "active_recall": a.get("active_recall")
            }

        import uuid
        turn_id = str(uuid.uuid4())
        snapshot = {
            "turn_id": turn_id,
            "status": "pending",
            "fallback_reason": None,
            "retry_attempts": 0,
            "mode": mode,
            "actions": [_serialize_action(a) for a in actions],
            "pre_turn": {
                "location": session.get("current_location", ""),
                "narrative": session.get("narrative", ""),
                "scene_title": session.get("scene_title", ""),
                "npcs": session.get("current_npcs", []),
                "enemies": session.get("nearby_enemies", [])
            },
            "applied": {}
        }
        await adb(db.set_turn_snapshot, session_id, snapshot)

        # Resolve the turn with the LLM — resolve_turn now always returns a dict
        try:
            outcome = await game_engine.resolve_turn(session, party, actions, stream_callback=stream_callback)
        except BaseException as e:
            # Mark hard failure
            snapshot["status"] = "failed_hard"
            snapshot["fallback_reason"] = "models_unavailable" # Simplified for now
            await adb(db.set_turn_snapshot, session_id, snapshot)
            raise e

        # Apply mechanics — apply_outcome also does its own coercion, but outcome is already a dict here
        items_gained = await adb(game_engine.apply_outcome, session_id, party, outcome, mp_already_spent, actions=actions)
        if not isinstance(items_gained, dict):
            items_gained = {}

        # Apply quest updates
        try:
            await adb(game_engine.apply_quest_update, session_id, outcome)
        except Exception as e:
            log.warning("apply_quest_update failed (non-fatal): %s", e)

        # Re-tag quest choices now that arrival/skill_check waypoint progression has unlocked next stages
        if isinstance(outcome, dict) and not (game_engine.get_active_enemies(session) or game_engine.get_active_enemies(outcome)):
            try:
                from mechanics.world.waypoints import tag_and_enrich_quest_choices
                lead_char = party[0][0] if party and party[0] else None
                raw_c = outcome.get("next_choices") or outcome.get("choices") or []
                eff_loc = outcome.get("location") or session.get("current_location", "")
                eff_dp = outcome.get("dialogue_partners") if "dialogue_partners" in outcome else outcome.get("dialogue_partner", ...)
                eff_npcs = outcome.get("npcs_present")
                enriched_c = await adb(
                    tag_and_enrich_quest_choices,
                    raw_c,
                    session_id,
                    eff_loc,
                    scen_key=session.get("scenario", "fantasy"),
                    char=lead_char,
                    dialogue_partner=eff_dp,
                    current_npcs=eff_npcs,
                )
                if enriched_c:
                    free_actions = [c for c in raw_c if isinstance(c, dict) and c.get("stat") == "FREE"]
                    final_c = enriched_c[:5]
                    for fa in free_actions:
                        if not any(fc.get("label") == fa.get("label") for fc in final_c if isinstance(fc, dict)):
                            final_c.append(fa)
                    outcome["next_choices"] = final_c
                    outcome["choices"] = final_c
            except Exception as e:
                log.warning("tag_and_enrich_quest_choices post-update failed (non-fatal): %s", e)

        # Apply merchant encounter state if present in outcome
        if isinstance(outcome, dict) and "merchant_encounter" in outcome:
            try:
                await adb(apply_merchant_encounter_result, session_id, outcome.get("merchant_encounter"))
            except Exception as e:
                log.warning("apply_merchant_encounter_result failed (non-fatal): %s", e)

        # Calculate XP
        xp_gained = 0
        levels_gained = []
        char = await adb(db.get_character, user_id)

        for a in actions:
            uid = a.get("user_id", user_id)
            char_for_xp = await adb(db.get_character, uid)
            if not char_for_xp:
                continue

            # Base XP from skill check tier
            check = a.get("check")
            if isinstance(check, dict):
                check_tier = check.get("tier", "fail")
            elif hasattr(check, "tier"):
                check_tier = check.tier
            else:
                check_tier = a.get("tier", "fail")
            base_xp = XP_REWARDS.get(check_tier, 0)

            # Bonus XP from character outcomes (LLM narrative rewards)
            bonus_xp = 0
            for co in outcome.get("character_outcomes", []):
                co_name = co.get("name", "") if isinstance(co, dict) else getattr(co, "name", "")
                if co_name.lower() == char_for_xp["name"].lower():
                    raw_xp = co.get("xp_change", 0) if isinstance(co, dict) else getattr(co, "xp_change", 0)
                    bonus_xp = int(raw_xp or 0)
                    break

            total_xp = base_xp + bonus_xp
            lvls = await adb(db.add_xp, uid, total_xp)

            if uid == user_id:
                xp_gained = total_xp
                levels_gained = lvls

        # Build history entry
        def compact_summary(text: str, max_chars: int = 500) -> str:
            t = str(text).strip()
            return t[:max_chars] + "..." if len(t) > max_chars else t

        outcome_only_nar = str(outcome.get("outcome_narrative") or "").strip()
        next_only_nar = str(outcome.get("next_narrative") or outcome.get("narrative") or "").strip()
        outcome_nar = outcome_only_nar or next_only_nar
        next_scene_title = str(outcome.get("scene_title") or session.get("scene_title") or "").strip()
        check = action.get("check")
        tier_label = check.tier_label if hasattr(check, "tier_label") else action.get("tier", "action")
        label = action.get("label", "Action")

        char_name = char["name"] if char else "Hero"
        
        # Determine witnesses
        witnesses = [char_name]
        npcs_present = outcome.get("npcs_present") or []
        for npc in npcs_present:
            n_name = game_engine._get_npc_name(npc)
            if n_name and n_name.lower() != "none" and n_name not in witnesses:
                witnesses.append(n_name)
        
        history_entry = {
            "type": "action",
            "character_name": char_name,
            "label": label,
            "tier": check.tier if hasattr(check, "tier") else action.get("tier", "action"),
            "tier_label": tier_label,
            "stat": action.get("stat"),
            "roll": check.roll if hasattr(check, "roll") else action.get("roll"),
            "chance": check.chance if hasattr(check, "chance") else action.get("rate"),
            "requirement": action.get("requirement"),
            "success": check.succeeded if hasattr(check, "succeeded") else action.get("success", False),
            "narrative": outcome_nar,
            "outcome_narrative": outcome_only_nar,
            "next_narrative": next_only_nar,
            "scene_title": next_scene_title,
            "location": outcome.get("location") or session.get("current_location") or "",
            "items_gained": items_gained.get(user_id, []),
            "xp_gained": xp_gained,
            "levels_gained": levels_gained,
            "mp_spent": action.get("mp_spent", 0),
            "character_outcomes": outcome.get("character_outcomes") or [],
            "relationship_updates": outcome.get("relationship_updates") or [],
            "faction_updates": outcome.get("faction_updates") or [],
            "quest_updates": outcome.get("quest_updates") or [],
            "witnessed_by": witnesses,
        }
        combat_log = outcome.get("combat_log") or outcome.get("_combat_log")
        if combat_log:
            history_entry["combat_log"] = combat_log
        if outcome.get("_enemy_attack_notice"):
            history_entry["enemy_attack_notice"] = outcome["_enemy_attack_notice"]

        raw_hist = list(session.get("history") or [])
        if not raw_hist and session.get("narrative"):
            raw_hist.append({
                "type": "scene",
                "scene_title": session.get("scene_title") or "Beginning",
                "narrative": session.get("narrative") or "",
                "next_narrative": session.get("narrative") or "",
                "location": session.get("current_location") or "",
            })

        has_dialogue = bool(outcome.get("dialogue_partners") or outcome.get("dialogue_partner"))
        dyn_limit = 12 if has_dialogue else 4
        new_hist = game_engine.push_history(raw_hist, history_entry, limit=dyn_limit)
        await adb(db.update_session, session_id, history_json=json.dumps(new_hist, default=str))

        fresh_session = await adb(db.get_session, session_id)
        new_char = await adb(db.get_character, user_id)

        if user_id not in items_gained:
            items_gained[user_id] = []

        snapshot["status"] = "completed"
        snapshot["applied"] = {
            "character_outcomes": outcome.get("character_outcomes", []),
            "items_gained": items_gained,
            "xp_gained": {uid: xp_gained if uid == user_id else 0 for uid in set([a.get("user_id", user_id) for a in actions])},
            "location": outcome.get("location", ""),
            "npcs_present": outcome.get("npcs_present", []),
            "nearby_enemies": outcome.get("nearby_enemies", []),
            "deceased_characters": outcome.get("deceased_characters", []),
            "dead_enemies": outcome.get("dead_enemies", []),
            "time_info": outcome.get("_time_info", {}),
            "sleep_info": outcome.get("_sleep_info"),
            "quest_updates": outcome.get("quest_updates", []),
            "relationship_updates": outcome.get("relationship_updates", [])
        }
        await adb(db.set_turn_snapshot, session_id, snapshot)

        base_response = TurnResponse(
            success=True,
            session=fresh_session,
            outcome=outcome,
            action=action,
            items_gained_by_user=items_gained,
            xp_gained=xp_gained,
            levels_gained=levels_gained,
            new_char=new_char
        )
        
        if outcome.get("_is_fallback_narrative"):
            log.info(f"Auto-recovery triggered for session {session_id} due to empty prose.")
            try:
                recovered_response = await TurnService.retry_narration(session_id, user_id, stream_callback=stream_callback)
                # Inherit the actual mechanical rewards from the base turn, since retry_narration zeros them out for UI
                recovered_response.items_gained_by_user = items_gained
                recovered_response.xp_gained = xp_gained
                recovered_response.levels_gained = levels_gained
                return recovered_response
            except Exception as e:
                log.warning("Auto-recovery narration pass failed: %s", e)
                snapshot["fallback_reason"] = "empty_prose"
                await adb(db.set_turn_snapshot, session_id, snapshot)
                base_response.outcome["fallback_reason"] = "empty_prose"
                return base_response
                
        return base_response

    @staticmethod
    async def retry_narration(session_id: int, user_id: int, stream_callback=None) -> TurnResponse:
        """Runs the lightweight narration pass for a retry, updating only prose and choices."""
        session = await adb(db.get_session, session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
            
        snapshot = await adb(db.get_turn_snapshot, session_id)
        if not snapshot or snapshot.get("status") != "completed":
            raise ValueError("No completed snapshot available to retry")
            
        attempt = snapshot.get("retry_attempts", 0) + 1
        
        from game_engine.turn.narration import run_narration_pass
        
        # Narration pass
        new_outcome = await run_narration_pass(session, snapshot, attempt=attempt, stream_callback=stream_callback)
        
        # We need to construct a complete TurnResponse
        # 1. Update the DB history directly like resolve_action does
        raw_hist = list(session.get("history") or [])
        if raw_hist and isinstance(raw_hist[-1], dict) and raw_hist[-1].get("type") == "action":
            last_entry = dict(raw_hist[-1])
            if new_outcome.get("outcome_narrative"):
                last_entry["outcome_narrative"] = new_outcome["outcome_narrative"]
                last_entry["narrative"] = new_outcome["outcome_narrative"]
            if new_outcome.get("next_narrative"):
                last_entry["next_narrative"] = new_outcome["next_narrative"]
            if new_outcome.get("scene_title"):
                last_entry["scene_title"] = new_outcome["scene_title"]
            raw_hist[-1] = last_entry
            await adb(db.update_session, session_id, history_json=json.dumps(raw_hist, default=str))

        # 2. Re-derive soft state
        # The choices will be sanitized by the caller usually, but we need to return them
        
        # Update snapshot attempts
        snapshot["retry_attempts"] = attempt
        # clear fallback_reason on manual retry
        snapshot["fallback_reason"] = None
        await adb(db.set_turn_snapshot, session_id, snapshot)
        
        fresh_session = await adb(db.get_session, session_id)
        new_char = await adb(db.get_character, user_id)
        
        # Merge new outcome with old applied mechanics so UI can display correctly if needed
        # (Though Web API only shows prose for retries, Discord might show embeds)
        merged_outcome = dict(snapshot.get("applied", {}))
        merged_outcome.update(new_outcome)
        
        # action is just the first action from snapshot for UI purposes
        action = snapshot.get("actions", [{}])[0]
        
        # items_gained_by_user and xp_gained are technically 0 for the *retry* itself, 
        # but we return empty to prevent double granting in UI
        return TurnResponse(
            success=True,
            session=fresh_session,
            outcome=merged_outcome,
            action=action,
            items_gained_by_user={},
            xp_gained=0,
            levels_gained=[],
            new_char=new_char
        )
