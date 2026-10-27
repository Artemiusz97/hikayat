from __future__ import annotations

import json
import logging
import asyncio
import re
from typing import Dict, List, Any, Optional
import httpx
from openai import APIError as OpenAIAPIError
from pydantic import BaseModel, ConfigDict
import db
from db import adb
import game_engine
from character_data import XP_REWARDS
from mechanics.combat.merchant import apply_merchant_encounter_result

log = logging.getLogger(__name__)
logger = log


def _is_llm_unavailable_exception(exc: BaseException) -> bool:
    """Return True only when an exception originates from upstream LLM/network unavailability."""
    if isinstance(exc, (OpenAIAPIError, httpx.HTTPError, TimeoutError, ConnectionError, asyncio.TimeoutError)):
        return True
    if isinstance(exc, RuntimeError) and "all llm candidate models in fallback chain failed" in str(exc).lower():
        return True
    cause = getattr(exc, "__cause__", None)
    if cause is not None and cause is not exc:
        return _is_llm_unavailable_exception(cause)
    return False


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
                    chance=int(chk.get("chance") if chk.get("chance") is not None else 100),
                    roll=float(chk.get("roll") if chk.get("roll") is not None else 100.0),
                    tier=str(chk.get("tier") or "success"),
                    tier_label=str(chk.get("tier_label") or "Success"),
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
        req_skip_minutes = raw_pick.get("skip_minutes")
        req_sleep_mode = raw_pick.get("sleep_mode")
        is_item_action = bool(raw_pick.get("is_item_action") or raw_pick.get("stat") == "ITEM")
        is_stealth_req = bool(
            raw_pick.get("is_stealth")
            or (raw_pick.get("stance") == "stealth")
            or (isinstance(raw_pick.get("action"), dict) and (raw_pick["action"].get("is_stealth") or raw_pick["action"].get("stance") == "stealth"))
        )

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
            if not req_intent and nested.get("intent"):
                req_intent = nested.get("intent")
            if req_skip_minutes is None and nested.get("skip_minutes") is not None:
                req_skip_minutes = nested.get("skip_minutes")
            if not req_sleep_mode and nested.get("sleep_mode"):
                req_sleep_mode = nested.get("sleep_mode")

        user_settings = await adb(db.get_settings, user_id) or {}
        check_mode = user_settings.get("debug_check_mode", "off")
        dialogue_mode = user_settings.get("dialogue_mode", "balanced")

        chosen: Dict[str, Any] = {}
        classification: Dict[str, Any] = {}
        is_custom = False
        is_standalone_direct_choice = False
        action_type = "choice"

        if choices is None and isinstance(session, dict):
            choices = session.get("choices") or []

        if is_item_action and not direct_choice and choice_index is None:
            chosen = {
                "stat": "ITEM",
                "requirement": 0,
                "mp_cost": 0,
                "label": custom_text or f"Use {raw_pick.get('item_name', 'item')}",
                "action_category": "item",
                "intent": "general_action",
                "sub_intent": "use_item",
                "item_name": raw_pick.get("item_name", ""),
                "item": raw_pick.get("item"),
                "item_consumed": raw_pick.get("item_consumed", True),
            }
        elif choice_index is not None and isinstance(choices, list) and 0 <= choice_index < len(choices):
            chosen = dict(choices[choice_index])
        elif isinstance(direct_choice, dict) and direct_choice:
            chosen = dict(direct_choice)
            is_standalone_direct_choice = True
            # Strip privileged server-only spoofing keys on un-indexed client direct_choice payloads
            for _priv_k in (
                "quest_id",
                "sub_obj_id",
                "stage_index",
                "is_quest_action",
                "is_climax_action",
                "is_story_quest",
                "_python_verified_quest",
                "triggers_loot_roll",
                "breakthrough_leveraged",
                "_server_stamped",
                "clue_pair_ids",
            ):
                chosen.pop(_priv_k, None)
            if chosen.get("spell_id"):
                try:
                    from mechanics.combat.spells.registry import get_spell
                    sp_def = get_spell(str(chosen["spell_id"]))
                    if isinstance(sp_def, dict) and sp_def.get("mp_cost") is not None:
                        chosen["mp_cost"] = int(sp_def["mp_cost"])
                except Exception:
                    pass
            if chosen.get("target_node_id") and session_id:
                cand_nid = str(chosen["target_node_id"])
                wn_row = await adb(db.get_world_node, session_id, cand_nid)
                if not wn_row:
                    chosen.pop("target_node_id", None)
        elif choice_index is not None:
            if not enforce_explicit_mp and isinstance(choices, list) and choices:
                chosen = dict(choices[0])
            elif not enforce_explicit_mp:
                chosen = {"stat": "PER", "requirement": 6, "mp_cost": 0, "label": "Proceed forward"}
            else:
                raise ValueError("Must provide choice_index, direct_choice, or custom_action_text")
        elif custom_text:
            is_custom = True
            action_type = "custom"
            if req_skip_minutes is not None or req_sleep_mode in ("sleep", "nap", "wait") or req_intent in ("wait_time", "rest_sleep"):
                classification = {
                    "stat": "NONE",
                    "requirement": 0,
                    "mp_cost": 0,
                    "action_category": "rest" if req_sleep_mode in ("sleep", "nap") or req_intent == "rest_sleep" else "wait",
                    "intent": req_intent or ("rest_sleep" if req_sleep_mode in ("sleep", "nap") else "wait_time"),
                }
                chosen = dict(classification)
                chosen["label"] = custom_text
                chosen["text"] = custom_text
            else:
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

        # ── Invariant 12 (A4): Restraint Hard-Gate on Travel / Movement ──────
        if session_id:
            try:
                from mechanics.world.locations.movement import is_movement_action
                from mechanics.social.physical_state import find_player_actor_key, can_actor_travel_or_dual_wield
                act_intent_low = str(chosen.get("intent") or req_intent or "").lower()
                is_break_attempt = act_intent_low in ("break_free", "companion_free") or any(
                    w in label_text.lower() for w in ("break free", "struggle", "slip out", "untie", "cut bonds", "cut my bonds")
                )
                if not is_break_attempt and (act_intent_low in ("movement", "travel", "fast_travel") or is_movement_action(label_text)):
                    phys_now = await adb(db.get_session_physical_state, session_id)
                    if phys_now and isinstance(phys_now.get("actors"), dict):
                        pk_now = find_player_actor_key(phys_now["actors"], party=[char], session_id=session_id)
                        p_actor_now = phys_now["actors"].get(pk_now) if pk_now else None
                        if p_actor_now:
                            can_move, move_reason = can_actor_travel_or_dual_wield(p_actor_now)
                            if not can_move:
                                raise ValueError(move_reason)
            except ValueError:
                raise
            except Exception:
                pass

        # ── MP Validation & Improvisation Rule (staged for atomic commit) ─────
        if mp_cost > 0:
            if char.get("mp", 0) < mp_cost:
                if not is_custom and enforce_explicit_mp:
                    raise PermissionError("Not enough MP for this action!")
                # Freeform custom text (or Discord fallback): improvise with 0 MP and +2 DC penalty
                label_text += " (couldn't afford the full effort, improvised instead)"
                mp_spent = 0
                if stat not in ("NONE", "FREE", "ITEM"):
                    req_val += 2

        # ── Gold Spending / Bribe Clamping Rule (staged for atomic commit) ───
        requested_gold = int(
            chosen.get("gold_spent")
            or chosen.get("gold_cost")
            or classification.get("gold_spent")
            or 0
        )
        avail_gold = max(0, int(char.get("gold", 0) or 0))
        actual_gold_spent = 0
        gold_shortfall_note = ""
        if requested_gold > 0 and requested_gold > avail_gold:
            req_val += 3
            gold_shortfall_note = (
                f"[SYSTEM NOTE: Player attempted to spend/offer {requested_gold} gold, "
                f"but only had {avail_gold} gold available (+3 DC penalty applied).]"
            )

        # ── Item Validation & Staged Consumption Rule ────────────────────────
        target_item_name = raw_pick.get("item_name") or chosen.get("item_name") or ""
        target_item_obj = raw_pick.get("item") or chosen.get("item")
        item_was_consumed = bool(chosen.get("item_consumed", False))

        if stat == "ITEM":
            inventory = await adb(db.get_inventory, user_id)
            if not target_item_name and not target_item_obj:
                label_lower = label_text.lower()
                for inv_item in (inventory or []):
                    iname = inv_item.get("name", "")
                    if iname and iname.lower() in label_lower:
                        target_item_name = iname
                        target_item_obj = inv_item
                        break
            if not target_item_name and isinstance(target_item_obj, dict):
                target_item_name = target_item_obj.get("name", "")
            if target_item_name:
                verified_inv_item = next(
                    (i for i in (inventory or []) if i.get("name", "").lower() == target_item_name.lower()),
                    None,
                )
                if verified_inv_item is not None:
                    target_item_obj = verified_inv_item
                elif is_standalone_direct_choice and enforce_explicit_mp:
                    raise PermissionError(f"Item '{target_item_name}' is not in your inventory!")
            if target_item_name and chosen.get("item_consumed", True) and target_item_obj is not None:
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
            import namegen
            act_lbl = label_text.lower()
            named_dps = [
                dp for dp in sess_dp
                if dp and (
                    dp.lower() in act_lbl
                    or any(
                        re.search(rf"\b{re.escape(tok)}\b", act_lbl)
                        for tok in namegen.get_unique_person_tokens(dp, peer_names=sess_dp, min_len=2)
                    )
                )
            ]
            if len(named_dps) == 1:
                explicit_target = named_dps[0]

        target_candidates = [explicit_target] if explicit_target else list(sess_dp)
        if target_candidates and isinstance(session, dict) and session.get("id") and stat not in ("NONE", "FREE", "ITEM"):
            is_romantic_attempt = (
                act_cat in ("romantic_confession", "affection", "intimate_act")
                or any(
                    kw in label_text.lower()
                    for kw in ("confess", "kiss", "flirt", "seduc", "intimate", "make out", "ask out", "romantic")
                )
            )
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
                    if is_romantic_attempt:
                        try:
                            from mechanics.social import relationship_graph as rg
                            curr_p = await adb(rg.get_current_partner, session["id"], rg.canonical_person_key(dp_name))
                            if curr_p and not rg.is_player_person_key(curr_p.get("person_key")):
                                req_val += 3
                        except Exception:
                            pass

        if stat not in ("NONE", "FREE", "ITEM") and req_val > 0:
            req_val = max(1, req_val)

        # ── Urgent Schedule Departure Hurry & Stage 2 Custom Auto-Fail ───────
        stage2_custom_auto_fail = False
        if target_candidates and isinstance(session, dict):
            from mechanics.social.conversation_choices import get_npc_departure_states, is_convince_stay_action
            from mechanics.narrative.intent import is_conversational_exit
            dep_states = get_npc_departure_states(session)
            if dep_states:
                for dp_name in target_candidates:
                    if not dp_name:
                        continue
                    dp_st = dep_states.get(re.sub(r"\s+", " ", str(dp_name).strip().lower()))
                    if not dp_st:
                        continue
                    stg = str(dp_st.get("stage") or "")
                    if stg == "stage_2_ultimatum" and is_custom:
                        stage2_custom_auto_fail = True
                        if stat in ("NONE", "FREE", ""):
                            stat = "CHA"
                        req_val = max(12, req_val)
                        break
                    elif stg == "stage_1_warning" and is_custom and not is_conversational_exit(label_text):
                        if is_convince_stay_action(label_text):
                            stat = "CHA"
                            req_val = max(6, req_val or 9)
                        elif stat in ("NONE", "FREE", "") or req_val <= 0:
                            stat = "CHA"
                            req_val = 9
                        elif stat != "ITEM":
                            req_val = min(15, max(7, req_val + 3))
                        break

        # ── Roll Skill Check ─────────────────────────────────────────────────
        stat_col = db.STAT_COLUMN.get(stat, "str_" if not is_custom else "agi_")
        hit_chance = chosen.get("hit_chance")
        if stage2_custom_auto_fail:
            res = skill_check.CheckResult(
                chance=0, roll=100.0, tier="fail", tier_label="Failed", succeeded=False, requirement=req_val
            )
            rate = 0
        elif stat == "ITEM":
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
        act_sub_intent = chosen.get("sub_intent") or (classification.get("sub_intent") if is_custom else "") or ""
        act_ends_dialogue = bool(chosen.get("ends_dialogue") or (classification.get("ends_dialogue") if is_custom else False))

        intent_source = "choice_tag" if (not is_custom and chosen.get("intent")) else ("utility_llm" if is_custom else "fallback")
        if not act_cat or act_cat == "custom" or not act_intent:
            if not act_intent:
                logger.warning("[TurnService] Action missing structured intent; falling back to regex classifier for '%s'", label_text)
                intent_source = "regex_fallback"
            parsed_i = classify_action_intent(label_text)
            if not act_cat or act_cat == "custom":
                act_cat = classification.get("action_category") or parsed_i.category.value
            if not act_intent:
                act_intent = parsed_i.category.value
            if not act_target and parsed_i.target_entity:
                act_target = parsed_i.target_entity
            if not act_sub_intent and parsed_i.sub_target:
                act_sub_intent = parsed_i.sub_target

        if act_intent == "dialogue_exit":
            act_ends_dialogue = True

        resolved_intent = {
            "intent": act_intent,
            "sub_intent": act_sub_intent,
            "target_npc": act_target or "",
            "ends_dialogue": act_ends_dialogue,
            "source": intent_source,
        }

        # ── Stealth Stance & Covert Action Resolution ─────────────────────────
        from mechanics.combat import is_in_combat as _ts_is_in_combat
        from mechanics.stealth import (
            get_session_stealth_state,
            is_actor_hidden,
            toggle_stealth_stance,
            break_stealth,
            apply_stealth_decay_turn,
            resolve_distraction_action,
            resolve_stealth_action,
            resolve_scene_environment_context,
        )

        st_state = get_session_stealth_state(session)
        prev_stealth_state = json.loads(json.dumps(st_state, default=str)) if isinstance(st_state, dict) else {}
        in_combat_now = bool(isinstance(session, dict) and _ts_is_in_combat(session))
        is_covert_intent = bool(act_intent == "stealth_covert" or act_cat == "stealth")
        actor_hidden_before = is_actor_hidden(session, user_id)
        effective_stealth = bool(
            is_stealth_req
            or is_covert_intent
            or (actor_hidden_before and raw_pick.get("stance") != "normal")
        )

        lbl_low = label_text.lower()
        stealth_outcome = None

        if not in_combat_now and isinstance(session, dict):
            # Assemble party + active companions for accurate companion noise math
            stealth_party = [(dict(char), [])]
            for comp_list_key in ("party_npcs", "temporary_companions"):
                for comp in (session.get(comp_list_key) or []):
                    if isinstance(comp, dict):
                        stealth_party.append((comp, []))
            if session.get("id"):
                try:
                    co_uids = await adb(db.get_session_members, session["id"])
                    for m_uid in (co_uids or []):
                        if m_uid != user_id:
                            m_char = await adb(db.get_character, m_uid)
                            if m_char:
                                m_inv = await adb(db.get_inventory, m_uid)
                                stealth_party.append((dict(m_char), m_inv or []))
                except Exception:
                    pass

            actor_inventory = await adb(db.get_inventory, user_id)
            env_ctx = resolve_scene_environment_context(session)
            curr_min_st = session.get("current_minute", 480)
            base_req = int(chosen.get("requirement", req_val) or req_val) if not is_custom else int(classification.get("requirement", req_val) or req_val)
            dc_mod_stealth = max(0, int(req_val) - base_req)

            is_distraction_action = bool(
                is_covert_intent
                and any(k in lbl_low for k in ("distract", "diversion", "throw stone", "throw a stone", "small stone", "pebble", "noise distraction", "divert attention"))
            )
            is_freeze_blend_action = bool(
                effective_stealth
                and any(k in lbl_low for k in ("freeze & blend", "hold motionless", "hold still", "stay still in shadow"))
            )

            if is_distraction_action:
                if not is_actor_hidden(session, user_id) and is_stealth_req:
                    toggle_stealth_stance(session, True, user_id=user_id)
                stealth_outcome = resolve_distraction_action(
                    session=session,
                    actor_char=char,
                    equipped_items=actor_inventory,
                    current_minute=curr_min_st,
                    party=stealth_party,
                    environment=env_ctx,
                    check_mode=check_mode,
                    user_id=user_id,
                )
                res = stealth_outcome["check"]
                rate = res.chance
                effective_stealth = is_actor_hidden(session, user_id) or bool(is_stealth_req or is_covert_intent)
                if session.get("id"):
                    await adb(db.update_session, session["id"], stealth_state=session["stealth_state"])
            elif is_freeze_blend_action:
                toggle_stealth_stance(session, True, user_id=user_id)
                apply_stealth_decay_turn(session, is_waiting_still=True)
                if session.get("id"):
                    await adb(db.update_session, session["id"], stealth_state=session["stealth_state"])
            elif effective_stealth:
                is_loud_magic = bool(
                    (chosen.get("spell_id") or act_cat == "magic")
                    and not any(k in lbl_low for k in ("silent", "shadow", "stealth", "invisib", "muffle", "veil"))
                )
                if act_intent in ("rest_sleep", "dialogue_init"):
                    break_stealth(session, reason=act_intent, user_id=user_id)
                    effective_stealth = False
                    if session.get("id"):
                        await adb(db.update_session, session["id"], stealth_state=session["stealth_state"])
                elif is_loud_magic:
                    break_stealth(session, reason="unsuppressed_magic", user_id=user_id)
                    effective_stealth = False
                    if session.get("id"):
                        await adb(db.update_session, session["id"], stealth_state=session["stealth_state"])
                else:
                    if not is_actor_hidden(session, user_id):
                        toggle_stealth_stance(session, True, user_id=user_id)
                    is_covert_check = bool(
                        is_covert_intent
                        or any(w in lbl_low for w in ("sneak", "creep", "infiltrate", "pickpocket", "shadow step", "silent takedown", "slip past", "lockpick", "pick the lock"))
                        or (stat == "AGI" and not any(w in lbl_low for w in ("flee", "sprint", "dodge", "chase")))
                    )
                    if is_covert_check:
                        stealth_outcome = resolve_stealth_action(
                            session=session,
                            actor_char=char,
                            action_data={
                                "label": label_text,
                                "action_type": chosen.get("choice_type", "stealth"),
                                "custom_action_text": label_text,
                                "target_npc": act_target,
                            },
                            target_entity={"name": act_target} if act_target else None,
                            party=stealth_party,
                            equipped_items=actor_inventory,
                            current_minute=curr_min_st,
                            environment=env_ctx,
                            check_mode=check_mode,
                            dc_modifier=dc_mod_stealth,
                            user_id=user_id,
                        )
                        res = stealth_outcome["check"]
                        rate = res.chance
                        effective_stealth = is_actor_hidden(session, user_id)
                    else:
                        apply_stealth_decay_turn(session, is_waiting_still=("wait" in lbl_low))
                    if session.get("id"):
                        await adb(db.update_session, session["id"], stealth_state=session["stealth_state"])

        # D7: Deduct gold_spent only on succeeded checks OR gamble forfeitures (staged for atomic commit)
        if requested_gold > 0:
            should_spend_gold = bool(res.succeeded or str(act_sub_intent or "").lower() == "gamble")
            actual_gold_spent = min(requested_gold, avail_gold) if should_spend_gold else 0

        act_dismisses_npc = str(
            chosen.get("dismisses_npc")
            or (classification.get("dismisses_npc") if is_custom else "")
            or ""
        ).strip()
        raw_skip = req_skip_minutes if req_skip_minutes is not None else (
            chosen.get("skip_minutes") if chosen.get("skip_minutes") is not None else chosen.get("wait_minutes")
        )
        action = dict(chosen) if not is_custom else {}
        action.update({
            "user_id": user_id,
            "character_name": char.get("name", "Player"),
            "char": dict(char),
            "stat": stat,
            "requirement": req_val,
            "mp_cost": mp_cost,
            "mp_spent": mp_spent,
            "_mp_already_deducted": False,
            "gold_spent": actual_gold_spent,
            "_requested_gold": requested_gold,
            "_gold_already_deducted": False,
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
            "choice_type": chosen.get("choice_type") or "",
            "action_category": act_cat,
            "intent": act_intent,
            "sub_intent": act_sub_intent,
            "target_npc": act_target or "",
            "ends_dialogue": act_ends_dialogue,
            "dismisses_npc": act_dismisses_npc,
            "_stage2_custom_auto_fail": stage2_custom_auto_fail,
            "resolved_intent": resolved_intent,
            "spell_id": chosen.get("spell_id") or "",
            "combat_target": combat_target or chosen.get("combat_target") or (classification.get("combat_target") if is_custom else None),
            "combat_tactical_archetype": chosen.get("combat_tactical_archetype") or (classification.get("combat_tactical_archetype", "") if is_custom else "") or "",
            "target_node_id": chosen.get("target_node_id") or "",
            "target_location": chosen.get("target_location") or (classification.get("target_location", "") if is_custom else "") or "",
            "spawns_npc_role": chosen.get("spawns_npc_role") or (classification.get("spawns_npc_role", "") if is_custom else "") or "",
            "triggers_loot_roll": bool(chosen.get("triggers_loot_roll") or (classification.get("triggers_loot_roll", False) if is_custom else False)),
            "is_quest_action": bool(chosen.get("is_quest_action", False)),
            "is_climax_action": bool(chosen.get("is_climax_action", False)),
            "breakthrough_leveraged": bool(chosen.get("breakthrough_leveraged", False)),
            "clue_pair_ids": list(chosen.get("clue_pair_ids") or []),
            "quest_id": chosen.get("quest_id") or "",
            "sub_obj_id": chosen.get("sub_obj_id"),
            "stage_index": chosen.get("stage_index"),
            "contract_type": chosen.get("contract_type") or "",
            "item_name": target_item_name,
            "item": target_item_obj,
            "item_consumed": item_was_consumed,
            "_item_already_removed": False,
            "active_recall": classification.get("_active_recall") if is_custom else chosen.get("_active_recall"),
            "is_stealth": effective_stealth,
            "stance": "stealth" if effective_stealth else "normal",
            "stealth_state": session.get("stealth_state") if isinstance(session, dict) else None,
            "_prev_stealth_state": prev_stealth_state,
            "stealth_outcome": stealth_outcome,
            "skip_minutes": int(raw_skip) if raw_skip not in (None, "") else 0,
            "sleep_mode": str(req_sleep_mode or chosen.get("sleep_mode") or ""),
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
            mp_already_spent = {
                a.get("user_id", user_id): a.get("mp_spent", 0)
                for a in actions
                if a.get("_mp_already_deducted")
            }
            await adb(db.update_session, session_id, pending_picks_json="{}")
        else:
            actions = [action]
            mp_already_spent = (
                {user_id: action.get("mp_spent", 0)}
                if action.get("_mp_already_deducted")
                else {}
            )

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
                "gold_spent": a.get("gold_spent", 0),
                "check": check_dict,
                "item_name": a.get("item_name"),
                "intent": a.get("intent"),
                "sub_intent": a.get("sub_intent"),
                "ends_dialogue": a.get("ends_dialogue", False),
                "dismisses_npc": a.get("dismisses_npc", ""),
                "target_name": a.get("target_name") or a.get("target_npc") or a.get("combat_target"),
                "target_npc": a.get("target_npc") or a.get("target_name") or a.get("combat_target"),
                "combat_target": a.get("combat_target") or a.get("target_npc") or a.get("target_name"),
                "target_node_id": a.get("target_node_id") or "",
                "target_location": a.get("target_location") or "",
                "spell_id": a.get("spell_id"),
                "quest_id": a.get("quest_id"),
                "sub_obj_id": a.get("sub_obj_id"),
                "stage_index": a.get("stage_index"),
                "breakthrough_leveraged": bool(a.get("breakthrough_leveraged", False)),
                "clue_pair_ids": list(a.get("clue_pair_ids") or []),
                "active_recall": a.get("active_recall"),
                "is_stealth": a.get("is_stealth", False),
                "stance": a.get("stance", "normal"),
                "stealth_state": a.get("stealth_state"),
                "stealth_outcome": {
                    k: (v.__dict__ if hasattr(v, "__dict__") and not isinstance(v, dict) else v)
                    for k, v in a["stealth_outcome"].items()
                } if isinstance(a.get("stealth_outcome"), dict) else None,
            }

        import uuid
        turn_id = str(uuid.uuid4())
        prev_st_rollback = None
        for a in actions:
            if isinstance(a, dict) and isinstance(a.get("_prev_stealth_state"), dict):
                prev_st_rollback = a.get("_prev_stealth_state")
                break
        snapshot = {
            "turn_id": turn_id,
            "status": "pending",
            "fallback_reason": None,
            "retry_attempts": 0,
            "mode": mode,
            "actions": [_serialize_action(a) for a in actions],
            "pre_turn": {
                "location": session.get("current_location", ""),
                "current_node_id": session.get("current_node_id", ""),
                "focal_point": session.get("focal_point", ""),
                "narrative": session.get("narrative", ""),
                "scene_title": session.get("scene_title", ""),
                "npcs": list(session.get("current_npcs") or []),
                "enemies": list(session.get("nearby_enemies") or []),
                "stealth_state": prev_st_rollback,
            },
            "applied": {}
        }
        await adb(db.set_turn_snapshot, session_id, snapshot)

        # Resolve the turn with the LLM — resolve_turn now always returns a dict
        try:
            outcome = await game_engine.resolve_turn(session, party, actions, stream_callback=stream_callback)
            if isinstance(outcome, dict) and isinstance(session, dict) and "stealth_state" not in outcome:
                outcome["stealth_state"] = session.get("stealth_state")
        except BaseException as e:
            if prev_st_rollback is not None:
                try:
                    await adb(db.update_session, session_id, stealth_state=prev_st_rollback)
                except Exception:
                    pass
            if isinstance(e, Exception):
                log.error("Hard failure during resolve_turn for session %s: %s", session_id, e, exc_info=True)
            snapshot["status"] = "failed_hard"
            if _is_llm_unavailable_exception(e):
                snapshot["fallback_reason"] = "models_unavailable"
            else:
                snapshot["fallback_reason"] = "engine_error"
                snapshot["error"] = f"{type(e).__name__}: {e}"
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

        deduction_xp_bonus = int(outcome.get("_deduction_xp_bonus") or 0) if isinstance(outcome, dict) else 0
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

            # Bonus XP from character outcomes + deterministic clue deduction
            bonus_xp = deduction_xp_bonus
            for co in outcome.get("character_outcomes", []):
                co_name = co.get("name", "") if isinstance(co, dict) else getattr(co, "name", "")
                if co_name.lower() == char_for_xp["name"].lower():
                    raw_xp = co.get("xp_change", 0) if isinstance(co, dict) else getattr(co, "xp_change", 0)
                    bonus_xp += int(raw_xp or 0)
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
            "is_fallback": bool(outcome.get("_is_fallback_narrative") or outcome.get("is_fallback")),
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
            "current_node_id": outcome.get("current_node_id") or fresh_session.get("current_node_id", ""),
            "focal_point": outcome.get("focal_point") or fresh_session.get("focal_point", ""),
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
            "cast_state": outcome.get("_staged_cast_state") or fresh_session.get("cast_state"),
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
        """Runs the lightweight narration pass for a retry, updating only prose and choices while freezing cast & spatial state (D13)."""
        session = await adb(db.get_session, session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
            
        snapshot = await adb(db.get_turn_snapshot, session_id)
        if not snapshot or snapshot.get("status") != "completed":
            raise ValueError("No completed snapshot available to retry")
            
        attempt = snapshot.get("retry_attempts", 0) + 1
        
        from game_engine.turn.narration import run_narration_pass
        
        # Narration pass (cast_events on retry output are strictly ignored per D13)
        new_outcome = await run_narration_pass(session, snapshot, attempt=attempt, stream_callback=stream_callback)
        if isinstance(new_outcome, dict):
            new_outcome.pop("cast_events", None)
        
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

        # Update snapshot attempts
        snapshot["retry_attempts"] = attempt
        snapshot["fallback_reason"] = None
        await adb(db.set_turn_snapshot, session_id, snapshot)
        
        fresh_session = await adb(db.get_session, session_id)
        new_char = await adb(db.get_character, user_id)
        
        # D13: Preserve frozen mechanical, spatial & cast state from snapshot["applied"]
        applied_state = dict(snapshot.get("applied", {}))
        merged_outcome = dict(applied_state)
        for k in ("outcome_narrative", "next_narrative", "scene_title", "next_choices", "choices", "_is_fallback_narrative"):
            if k in new_outcome:
                merged_outcome[k] = new_outcome[k]
        # Guarantee frozen cast & spatial fields cannot drift on retry
        for frozen_k in ("location", "current_node_id", "focal_point", "npcs_present", "dialogue_partner", "dialogue_partners"):
            if frozen_k in applied_state:
                merged_outcome[frozen_k] = applied_state[frozen_k]

        raw_retry_choices = merged_outcome.get("next_choices") or merged_outcome.get("choices") or []
        if raw_retry_choices and hasattr(game_engine, "build_hybrid_turn_choices"):
            try:
                rebuilt_choices = await adb(
                    game_engine.build_hybrid_turn_choices,
                    raw_retry_choices,
                    scenario=fresh_session.get("scenario", "fantasy"),
                    location=merged_outcome.get("location") or fresh_session.get("current_location", ""),
                    char=new_char,
                    dialogue_partner=merged_outcome.get("dialogue_partners")
                    if "dialogue_partners" in merged_outcome
                    else merged_outcome.get("dialogue_partner"),
                    current_npcs=merged_outcome.get("npcs_present") or fresh_session.get("current_npcs", []),
                    session_id=session_id,
                    session=fresh_session,
                )
                if rebuilt_choices:
                    merged_outcome["next_choices"] = rebuilt_choices
                    merged_outcome["choices"] = rebuilt_choices
                    merged_outcome["_hybrid_choices_built"] = True
            except Exception as e:
                log.warning("build_hybrid_turn_choices during retry_narration failed (non-fatal): %s", e)

        action = snapshot.get("actions", [{}])[0]
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
