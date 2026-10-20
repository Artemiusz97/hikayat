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
    async def prepare_and_roll_action(
        session_id: int,
        user_id: int,
        raw_pick: Dict[str, Any],
        session: Optional[Dict[str, Any]] = None,
        char: Optional[Dict[str, Any]] = None,
        choices: Optional[List[Dict[str, Any]]] = None,
        enforce_explicit_mp: bool = True,
    ) -> Dict[str, Any]:
        """
        Single source of truth for pre-turn action classification, MP/Item/Gold deduction,
        NPC trait & intimate DC modifiers, and deterministic skill check rolling across Web and Discord.
        """
        import random
        import skill_check
        from mechanics.narrative.intent import classify_action_intent
        from mechanics.world.mobility import get_session_dialogue_partners
        from mechanics.combat.traits import get_combined_dc_modifiers
        from mechanics.social.persona import calculate_intimate_action_dc_modifier

        # Idempotency guard: if raw_pick is already a resolved action with a CheckResult, return it directly
        if isinstance(raw_pick, dict) and raw_pick.get("check") is not None and raw_pick.get("char"):
            chk = raw_pick["check"]
            if isinstance(chk, dict):
                raw_pick = dict(raw_pick)
                raw_pick["check"] = skill_check.CheckResult(
                    chance=int(chk.get("chance", 100)),
                    roll=float(chk.get("roll", 100.0)),
                    tier=str(chk.get("tier", "success")),
                    tier_label=str(chk.get("tier_label", "Success")),
                    succeeded=bool(chk.get("succeeded", True)),
                    requirement=int(chk.get("requirement", raw_pick.get("requirement", 0)) or 0),
                )
            return raw_pick

        if session is None:
            sess_row = await adb(db.get_session, session_id)
            if not sess_row:
                raise ValueError(f"Session {session_id} not found")
            session = dict(sess_row)

        if char is None:
            char_row = await adb(db.get_character, user_id)
            if not char_row:
                raise LookupError("Character not found")
            char = dict(char_row)
        else:
            char = dict(char)

        # Normalize payload fields from Web or Discord
        choice_index = raw_pick.get("choice_index")
        custom_text = raw_pick.get("custom_action_text") or raw_pick.get("custom_text")
        direct_choice = raw_pick.get("direct_choice")
        combat_target = raw_pick.get("combat_target")
        req_intent = raw_pick.get("intent")
        req_target_npc = raw_pick.get("target_npc") or raw_pick.get("target_name")
        is_item_action = bool(raw_pick.get("is_item_action") or raw_pick.get("stat") == "ITEM")

        if isinstance(raw_pick.get("action"), dict):
            nested = raw_pick["action"]
            if choice_index is None and "choice_index" in nested:
                choice_index = nested.get("choice_index")
            if not custom_text:
                custom_text = nested.get("custom_action_text") or nested.get("custom_text")
            if direct_choice is None and isinstance(nested.get("direct_choice"), dict):
                direct_choice = nested.get("direct_choice")
            if not combat_target and nested.get("combat_target"):
                combat_target = nested.get("combat_target")

        user_settings = await adb(db.get_settings, user_id) or {}
        check_mode = user_settings.get("debug_check_mode", "off")
        dialogue_mode = user_settings.get("dialogue_mode", "balanced")

        chosen: Dict[str, Any] = {}
        classification: Dict[str, Any] = {}
        is_custom = False
        action_type = "choice"

        if is_item_action and not direct_choice and choice_index is None:
            chosen = {
                "stat": "ITEM",
                "requirement": 0,
                "mp_cost": 0,
                "label": custom_text or f"Use {raw_pick.get('item_name', 'item')}",
                "action_category": "item",
                "item_name": raw_pick.get("item_name", ""),
                "item": raw_pick.get("item"),
                "item_consumed": raw_pick.get("item_consumed", True),
            }
        elif isinstance(direct_choice, dict) and direct_choice:
            chosen = dict(direct_choice)
        elif choice_index is not None:
            if choices is None:
                choices = session.get("choices") or []
            if isinstance(choices, list) and 0 <= choice_index < len(choices):
                chosen = dict(choices[choice_index])
            elif not enforce_explicit_mp and isinstance(choices, list) and choices:
                chosen = dict(choices[0])
            elif not enforce_explicit_mp:
                chosen = {"stat": "PER", "requirement": 6, "mp_cost": 0, "label": "Proceed forward"}
            else:
                raise ValueError("Must provide choice_index, direct_choice, or custom_action_text")
        elif custom_text:
            is_custom = True
            action_type = "custom"
            inventory = await adb(db.get_inventory, user_id)
            classification = await game_engine.classify_custom_action(session, char, inventory, custom_text)
            if not isinstance(classification, dict):
                classification = dict(classification) if hasattr(classification, "items") else {}
            chosen = dict(classification)
            chosen["label"] = custom_text
            chosen["text"] = custom_text
        else:
            raise ValueError("Must provide choice_index, direct_choice, or custom_action_text")

        stat = str(chosen.get("stat", "STR") or "STR").upper()
        req_val = int(chosen.get("requirement", 5 if not is_custom else 6) or 0)
        mp_cost = int(chosen.get("mp_cost", 0) or 0)
        mp_spent = mp_cost
        label_text = str(chosen.get("label") or chosen.get("text") or custom_text or "Action")

        # ── MP Validation & Improvisation Rule ───────────────────────────────
        if mp_cost > 0:
            if char.get("mp", 0) < mp_cost:
                if not is_custom and enforce_explicit_mp:
                    raise PermissionError("Not enough MP for this action!")
                # Freeform custom text (or Discord fallback): improvise with 0 MP and +2 DC penalty
                label_text += " (couldn't afford the full effort, improvised instead)"
                mp_spent = 0
                if stat not in ("NONE", "FREE", "ITEM"):
                    req_val += 2
            else:
                await adb(db.apply_hp_mp_delta, user_id, mp_delta=-mp_cost)
                char["mp"] = max(0, int(char.get("mp", 0)) - mp_cost)

        # ── Gold Spending / Bribe Clamping Rule ──────────────────────────────
        requested_gold = int(chosen.get("gold_spent") or classification.get("gold_spent") or 0)
        actual_gold_spent = 0
        gold_shortfall_note = ""
        if requested_gold > 0:
            avail_gold = max(0, int(char.get("gold", 0) or 0))
            actual_gold_spent = min(requested_gold, avail_gold)
            if actual_gold_spent > 0:
                await adb(db.apply_hp_mp_delta, user_id, gold_delta=-actual_gold_spent)
                char["gold"] = avail_gold - actual_gold_spent
            if requested_gold > avail_gold:
                req_val += 3
                gold_shortfall_note = (
                    f"[SYSTEM NOTE: Player attempted to spend/offer {requested_gold} gold, "
                    f"but only had {avail_gold} gold available (+3 DC penalty applied).]"
                )

        # ── Item Consumption Rule ────────────────────────────────────────────
        target_item_name = raw_pick.get("item_name") or chosen.get("item_name") or ""
        target_item_obj = raw_pick.get("item") or chosen.get("item")
        item_was_consumed = bool(chosen.get("item_consumed", False))

        if stat == "ITEM":
            if not target_item_name and not target_item_obj:
                inventory = await adb(db.get_inventory, user_id)
                label_lower = label_text.lower()
                for inv_item in (inventory or []):
                    iname = inv_item.get("name", "")
                    if iname and iname.lower() in label_lower:
                        target_item_name = iname
                        target_item_obj = inv_item
                        break
            if not target_item_name and isinstance(target_item_obj, dict):
                target_item_name = target_item_obj.get("name", "")
            if not target_item_obj and target_item_name:
                inventory = await adb(db.get_inventory, user_id)
                target_item_obj = next(
                    (i for i in (inventory or []) if i.get("name", "").lower() == target_item_name.lower()),
                    None,
                )
            if target_item_name and chosen.get("item_consumed", True):
                await adb(db.remove_item_by_name, user_id, target_item_name)
                item_was_consumed = True

        # ── Dialogue & Persona DC Modifiers ──────────────────────────────────
        act_cat = str(chosen.get("action_category") or ("custom" if is_custom else "")).strip()
        if (
            chosen.get("choice_type") == "dialogue"
            or act_cat in ("dialogue", "romantic_confession", "social_invite", "party_recruit", "affection", "disclosure_inquiry")
        ):
            if dialogue_mode == "casual":
                req_val = max(1, req_val - 2)
            elif dialogue_mode == "challenging":
                req_val += 2

        sess_dp = get_session_dialogue_partners(session) if isinstance(session, dict) else []
        explicit_target = (
            combat_target
            or req_target_npc
            or chosen.get("target_npc")
            or (classification.get("target_npc") if is_custom else None)
        )
        if not explicit_target:
            act_lbl = label_text.lower()
            named_dps = [
                dp for dp in sess_dp
                if dp and (dp.lower() in act_lbl or (len(dp.split()[0]) >= 3 and dp.split()[0].lower() in act_lbl))
            ]
            if len(named_dps) == 1:
                explicit_target = named_dps[0]

        target_candidates = [explicit_target] if explicit_target else list(sess_dp)
        if target_candidates and isinstance(session, dict) and session.get("id") and stat not in ("NONE", "FREE", "ITEM"):
            for dp_name in target_candidates:
                if dp_name:
                    c_rec = await adb(db.get_contact, session["id"], str(dp_name).lower().replace(" ", "_"), char.get("id", 0))
                    if c_rec:
                        c_traits = c_rec.get("unlocked_traits") or c_rec.get("traits") or []
                        t_mods = get_combined_dc_modifiers(c_traits)
                        req_val += t_mods.get(stat, 0)
                        app_rec = c_rec.get("appearance", {})
                        if isinstance(app_rec, dict):
                            req_val += calculate_intimate_action_dc_modifier(label_text, app_rec)

        if stat not in ("NONE", "FREE", "ITEM") and req_val > 0:
            req_val = max(1, req_val)

        # ── Roll Skill Check ─────────────────────────────────────────────────
        stat_col = db.STAT_COLUMN.get(stat, "str_" if not is_custom else "agi_")
        hit_chance = chosen.get("hit_chance")
        if stat == "ITEM":
            res = skill_check.CheckResult(
                chance=100, roll=100.0, tier="success", tier_label="Item Used", succeeded=True, requirement=req_val
            )
            rate = 100
        elif hit_chance is not None:
            rate = int(hit_chance)
            roll = round(random.uniform(0, 100), 1)
            if check_mode == "always_crit_success":
                tier, succeeded = "crit_success", True
            elif check_mode == "always_success":
                tier, succeeded = "success", True
            elif check_mode == "always_fail":
                tier, succeeded = "fail", False
            elif check_mode == "always_crit_fail":
                tier, succeeded = "crit_fail", False
            else:
                succeeded = roll <= rate
                crit_s_thresh = max(1, rate // 5)
                if succeeded and roll <= crit_s_thresh:
                    tier = "crit_success"
                elif succeeded:
                    tier = "success"
                elif roll >= 95:
                    tier = "crit_fail"
                else:
                    tier = "fail"
            res = skill_check.CheckResult(
                chance=rate,
                roll=roll,
                tier=tier,
                tier_label=tier.replace("_", " ").title(),
                succeeded=succeeded,
                requirement=req_val,
            )
        elif stat in ("NONE", "FREE") or req_val <= 0:
            res = skill_check.CheckResult(
                chance=100, roll=100.0, tier="success", tier_label="Success", succeeded=True, requirement=req_val
            )
            rate = 100
        else:
            stat_val = char.get(stat_col, 5)
            luk_val = char.get("luk", 3)
            rate = skill_check.success_chance(stat_val, req_val, check_mode=check_mode)
            res = skill_check.resolve_check(stat_val, req_val, luk_val, check_mode=check_mode)

        # ── Intent & Category Normalization ──────────────────────────────────
        act_intent = req_intent or chosen.get("intent") or (classification.get("intent") if is_custom else None)
        act_target = req_target_npc or chosen.get("target_npc") or (classification.get("target_npc") if is_custom else None)
        if not act_cat or act_cat == "custom" or not act_intent:
            parsed_i = classify_action_intent(label_text)
            if not act_cat or act_cat == "custom":
                act_cat = classification.get("action_category") or parsed_i.category.value
            if not act_intent:
                act_intent = parsed_i.category.value
            if not act_target and parsed_i.target_entity:
                act_target = parsed_i.target_entity

        action = dict(chosen) if not is_custom else {}
        action.update({
            "user_id": user_id,
            "character_name": char.get("name", "Player"),
            "char": dict(char),
            "stat": stat,
            "requirement": req_val,
            "mp_cost": mp_cost,
            "mp_spent": mp_spent,
            "gold_spent": actual_gold_spent,
            "_gold_already_deducted": bool(actual_gold_spent > 0),
            "_gold_shortfall_note": gold_shortfall_note,
            "rate": rate,
            "check": res,
            "label": label_text,
            "success": res.succeeded,
            "tier": res.tier,
            "crit": res.tier in ("crit_success", "crit_fail"),
            "roll": res.roll,
            "text": label_text,
            "type": action_type,
            "choice_type": chosen.get("choice_type", ""),
            "action_category": act_cat,
            "spell_id": chosen.get("spell_id", ""),
            "combat_target": combat_target or chosen.get("combat_target") or (classification.get("combat_target") if is_custom else None),
            "combat_tactical_archetype": chosen.get("combat_tactical_archetype") or (classification.get("combat_tactical_archetype", "") if is_custom else ""),
            "target_location": chosen.get("target_location") or (classification.get("target_location", "") if is_custom else ""),
            "spawns_npc_role": chosen.get("spawns_npc_role") or (classification.get("spawns_npc_role", "") if is_custom else ""),
            "triggers_loot_roll": bool(chosen.get("triggers_loot_roll") or (classification.get("triggers_loot_roll", False) if is_custom else False)),
            "is_quest_action": bool(chosen.get("is_quest_action", False)),
            "is_climax_action": bool(chosen.get("is_climax_action", False)),
            "quest_id": chosen.get("quest_id", ""),
            "sub_obj_id": chosen.get("sub_obj_id"),
            "stage_index": chosen.get("stage_index"),
            "contract_type": chosen.get("contract_type", ""),
            "item_name": target_item_name,
            "item": target_item_obj,
            "item_consumed": item_was_consumed,
            "intent": act_intent,
            "sub_intent": chosen.get("sub_intent") or (classification.get("sub_intent", "") if is_custom else ""),
            "target_npc": act_target,
            "active_recall": classification.get("_active_recall") if is_custom else chosen.get("_active_recall"),
        })
        if not action.get("active_recall") and isinstance(session, dict) and session.get("id") and label_text:
            from game_engine.turn.generation import extract_deterministic_recall_query
            recall_q = extract_deterministic_recall_query(label_text, session_id=session["id"])
            if recall_q:
                from db.memory import active_recall_search
                recall_hits = await adb(active_recall_search, session["id"], recall_q)
                if recall_hits:
                    action["active_recall"] = recall_hits
        return action

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
                "target_name": a.get("target_name") or a.get("target_npc") or a.get("combat_target"),
                "target_npc": a.get("target_npc") or a.get("target_name") or a.get("combat_target"),
                "combat_target": a.get("combat_target") or a.get("target_npc") or a.get("target_name"),
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

        # Apply mechanics (includes quest & waypoint updates via _reduce_quests_and_waypoints)
        items_gained = await adb(game_engine.apply_outcome, session_id, party, outcome, mp_already_spent, actions=actions)
        if not isinstance(items_gained, dict):
            items_gained = {}

        # Re-tag quest choices now that arrival/skill_check waypoint progression has unlocked next stages
        from mechanics.social.physical_state import is_erotic_intimate_contact as _ts_is_erotic
        _ts_phys = (outcome.get("_physical_state") if isinstance(outcome, dict) else None) or {}
        _ts_ic_str = str(_ts_phys.get("intimate_contact", "") if isinstance(_ts_phys, dict) else "")
        _ts_in_intimate = _ts_is_erotic(_ts_ic_str) or ("aftercare" in _ts_ic_str.lower())
        # Only re-tag quest choices if a waypoint stage unlocked during apply_outcome
        if (
            isinstance(outcome, dict)
            and outcome.get("_waypoint_notices")
            and not outcome.get("_hybrid_choices_built")
            and not _ts_in_intimate
            and not (game_engine.get_active_enemies(session) or game_engine.get_active_enemies(outcome))
        ):
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
        if outcome.get("intimate_update"):
            history_entry["intimate_update"] = outcome["intimate_update"]
        if outcome.get("_refractory_recovered_notice"):
            history_entry["_refractory_recovered_notice"] = outcome["_refractory_recovered_notice"]

        raw_hist = list(session.get("history") or [])
        if not raw_hist and session.get("narrative"):
            raw_hist.append({
                "type": "scene",
                "scene_title": session.get("scene_title") or "Beginning",
                "narrative": session.get("narrative") or "",
                "next_narrative": session.get("narrative") or "",
                "location": session.get("current_location") or "",
                "scene_image_url": session.get("scene_image_url"),
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
            "relationship_updates": outcome.get("relationship_updates", []),
            "dialogue_partner": outcome.get("dialogue_partner"),
            "dialogue_partners": outcome.get("dialogue_partners", []),
            "intimate_update": outcome.get("intimate_update"),
            "_physical_state": outcome.get("_physical_state"),
            "_refractory_recovered_notice": outcome.get("_refractory_recovered_notice"),
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
            new_outcome_narr = (new_outcome.get("outcome_narrative") or "").strip()
            new_next_narr = (new_outcome.get("next_narrative") or "").strip()

            # Check if previous outcome_narrative was an emergency fallback
            prev_outcome = str(last_entry.get("outcome_narrative") or "")
            is_prev_fallback = (
                bool(last_entry.get("is_fallback") or last_entry.get("_is_fallback_narrative"))
                or any(ph in prev_outcome.lower() for ph in (
                    "deliberate intent",
                    "carefully observe",
                    "temporary fallback",
                    "threads of fate shimmer",
                    "fallback generation",
                ))
            )

            if new_outcome_narr:
                last_entry["outcome_narrative"] = new_outcome_narr
                last_entry["narrative"] = new_outcome_narr
                last_entry.pop("is_fallback", None)
                last_entry.pop("_is_fallback_narrative", None)
            elif is_prev_fallback:
                # If retry did not provide a separate outcome_narrative, clear the emergency fallback text
                # so the stale placeholder does not persist in the adventure history.
                last_entry["outcome_narrative"] = ""
                last_entry["narrative"] = new_next_narr or ""
                last_entry.pop("is_fallback", None)
                last_entry.pop("_is_fallback_narrative", None)

            if new_next_narr:
                last_entry["next_narrative"] = new_next_narr
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
        # Narration pass only updates prose and choices; preserve frozen mechanical state (location, NPCs, enemies, vitals)
        merged_outcome = dict(snapshot.get("applied", {}))
        for k in ("outcome_narrative", "next_narrative", "scene_title", "next_choices", "choices", "_is_fallback_narrative"):
            if k in new_outcome:
                merged_outcome[k] = new_outcome[k]
        
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
