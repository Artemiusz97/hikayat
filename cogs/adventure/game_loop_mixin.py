import discord
import asyncio
import db
import game_engine
from services.turn_service import TurnService
from .embeds import *
from .views.choices import ChoiceView, SyncChoiceView
from .embeds import _apply_merchant_encounter_result, _format_items_gained, _format_items_gained_multi, _is_dialogue_partner, _safe_int
from mechanics.system.concurrency import distributed_session_lock, LockAcquisitionError
import logging
logger = logging.getLogger(__name__)

class GameLoopMixin:
    async def _resolve_pick(self, session: dict, user_id: int, pick: dict) -> dict:
            """Turns a recorded pick (choice_index, direct_choice, or custom_text) into an
            action dict for game_engine.resolve_turn, spending MP as needed."""
            char, inventory = await asyncio.gather(
                adb(db.get_character, user_id),
                adb(db.get_inventory, user_id),
            )

            choice = {}
            action_cat = ""
            if pick.get("direct_choice"):
                choice = pick["direct_choice"]
                stat = choice.get("stat", "STR")
                requirement = choice.get("requirement", 0)
                mp_cost = choice.get("mp_cost", 0)
                label = choice.get("label", "Action")
                action_cat = choice.get("action_category", "")
            elif "choice_index" in pick:
                choices_list = session.get("choices") or []
                idx = pick["choice_index"]
                if isinstance(choices_list, list) and 0 <= idx < len(choices_list):
                    choice = choices_list[idx]
                elif isinstance(choices_list, list) and choices_list:
                    choice = choices_list[0]
                else:
                    choice = {"stat": "PER", "requirement": 6, "mp_cost": 0, "label": "Proceed forward"}
                stat, requirement, mp_cost, label = (choice.get("stat", "PER"), choice.get("requirement", 6),
                                                       choice.get("mp_cost", 0), choice.get("label", "Proceed forward"))
                action_cat = choice.get("action_category", "")
            elif pick.get("is_item_action") or pick.get("stat") == "ITEM":
                stat = "ITEM"
                requirement = 0
                mp_cost = 0
                label = pick.get("custom_text", "Use item")
                action_cat = "item"
            else:
                classification = await game_engine.classify_custom_action(session, char, inventory,
                                                                            pick["custom_text"])
                stat, requirement, mp_cost, label = (classification["stat"], classification["requirement"],
                                                       classification["mp_cost"], pick["custom_text"])
                action_cat = "custom"

            if mp_cost > char["mp"]:
                label += " (couldn't afford the full effort, improvised instead)"
                mp_cost = 0

            if mp_cost:
                await adb(db.apply_hp_mp_delta, user_id, hp_delta=0, mp_delta=-mp_cost)
                char = await adb(db.get_character, user_id)

            actor_settings = await adb(db.get_settings, user_id)
            check_mode = actor_settings.get("debug_check_mode", "off")
            target_item_name = pick.get("item_name") or choice.get("item_name")
            target_item_obj = pick.get("item") or choice.get("item")
            item_was_consumed = False

            if stat == "ITEM":
                if not target_item_name and not target_item_obj:
                    # Detect from action label / custom text against user's carried inventory
                    label_lower = label.lower()
                    for inv_item in inventory:
                        iname = inv_item.get("name", "")
                        if iname and iname.lower() in label_lower:
                            target_item_name = iname
                            target_item_obj = inv_item
                            break
                if not target_item_name and target_item_obj:
                    target_item_name = target_item_obj.get("name")
                if not target_item_obj and target_item_name:
                    target_item_obj = next((i for i in inventory if i.get("name", "").lower() == target_item_name.lower()), None)

                check = CheckResult(chance=100, roll=100.0, tier="success", tier_label="Item Used", succeeded=True, requirement=requirement)
                if target_item_name:
                    await adb(db.remove_item_by_name, user_id, target_item_name)
                    item_was_consumed = True
            elif action_cat in ("attack", "magic"):
                hit_chance = choice.get("hit_chance", 75)
                roll = random.uniform(0.01, 100.0)
                p_luk = char.get("luk", 3)
                crit_threshold = max(5, min(30, 5 + p_luk * 2))

                if check_mode == "always_crit_success":
                    tier = "crit_success"
                    succeeded = True
                elif check_mode == "always_success":
                    tier = "success"
                    succeeded = True
                elif check_mode == "always_fail":
                    tier = "fail"
                    succeeded = False
                elif check_mode == "always_crit_fail":
                    tier = "crit_fail"
                    succeeded = False
                elif roll <= crit_threshold:
                    tier = "crit_success"
                    succeeded = True
                elif roll <= hit_chance:
                    tier = "success"
                    succeeded = True
                else:
                    tier = "fail"
                    succeeded = False

                tier_label = "Critical Hit!" if tier == "crit_success" else ("Hit!" if tier == "success" else "Missed")
                check = CheckResult(chance=hit_chance, roll=roll, tier=tier, tier_label=tier_label, succeeded=succeeded, requirement=requirement)
            elif stat in ("NONE", "FREE") or requirement <= 0:
                check = CheckResult(chance=100, roll=100.0, tier="success", tier_label="Success", succeeded=True, requirement=requirement)
            else:
                stat_col = STAT_COLUMN.get(stat, "agi_")
                req = requirement
                from mechanics.world.mobility import get_session_dialogue_partners
                sess_dp = get_session_dialogue_partners(session) if isinstance(session, dict) else []
                if sess_dp and isinstance(session, dict) and session.get("id"):
                    from mechanics.combat.traits import get_combined_dc_modifiers
                    for dp_name in sess_dp:
                        if dp_name:
                            c_rec = db.get_contact(session["id"], str(dp_name).lower().replace(" ", "_"), char.get("id", 0))
                            if c_rec:
                                c_traits = c_rec.get("unlocked_traits") or c_rec.get("traits") or []
                                t_mods = get_combined_dc_modifiers(c_traits)
                                req += t_mods.get(stat, 0)
                                app_rec = c_rec.get("appearance", {})
                                if isinstance(app_rec, dict):
                                    from mechanics.social.persona import calculate_intimate_action_dc_modifier
                                    req += calculate_intimate_action_dc_modifier(label, app_rec)
                req = max(1, req)
                check = resolve_check(char.get(stat_col, 5), req, char.get("luk", 3), check_mode=check_mode)
            return {
                "char": char,
                "label": label,
                "check": check,
                "mp_spent": mp_cost,
                "stat": stat,
                "item_name": target_item_name,
                "item": target_item_obj,
                "item_consumed": item_was_consumed,
                "is_quest_action": bool(choice.get("is_quest_action")),
                "is_climax_action": bool(choice.get("is_climax_action")),
                "quest_id": choice.get("quest_id", ""),
                "sub_obj_id": choice.get("sub_obj_id"),
                "stage_index": choice.get("stage_index"),
                "contract_type": choice.get("contract_type", ""),
                "active_recall": classification.get("_active_recall") if action_cat == "custom" and isinstance(classification, dict) else None
            }

    async def handle_action(self, interaction: discord.Interaction, session_id: int,
                                 choice_index: int | None = None, custom_text: str | None = None,
                                 direct_choice: dict | None = None,
                                 is_item_action: bool = False, item_name: str | None = None, target_name: str | None = None):
            if not interaction.response.is_done():
                try:
                    await interaction.response.defer()
                except (discord.NotFound, discord.HTTPException):
                    pass

            try:
                async with distributed_session_lock(session_id, raise_http_error=False):
                    user_id = interaction.user.id
                    session = await adb(db.get_session, session_id)
                    if not session or session["status"] != "active":
                        await interaction.followup.send("This adventure isn't active anymore.", ephemeral=True)
                        return
                    if session.get("merchant", {}).get("active"):
                        await interaction.followup.send(
                            "🛍️ The party is currently browsing the merchant's stall! Finish or leave the shop before continuing the adventure.",
                            ephemeral=True)
                        return
                    if db.current_turn_user_id(session) != user_id:
                        await interaction.followup.send("It's not your turn anymore.", ephemeral=True)
                        return

                    if is_item_action:
                        pick = {
                            "is_item_action": True,
                            "item_name": item_name,
                            "target_name": target_name,
                            "custom_text": custom_text or f"Use {item_name} on {target_name}"
                        }
                    elif direct_choice is not None:
                        pick = {"direct_choice": direct_choice}
                    elif choice_index is not None:
                        pick = {"choice_index": choice_index}
                    else:
                        pick = {"custom_text": custom_text}

                    self._last_picks[session_id] = (user_id, pick)
                    try:
                        action = await self._resolve_pick(session, user_id, pick)
                    except Exception as e:
                        logger.error("Failed to interpret action for user %s in session %s: %s", user_id, session_id, e, exc_info=True)
                        await interaction.followup.send(f"⚠️ The LLM failed to interpret this action: {e}")
                        return

                    try:
                        # Wrap sync/async mismatch: TurnService.resolve_action is async, but db calls inside it are sync.
                        # Hikayat uses threaded DB calls or async wrappers for db.
                        # Actually, TurnService uses db directly which are synchronous sqlite calls, that's fine for now as server.py also does it.
                        turn_response = await TurnService.resolve_action(session_id, user_id, action, mode="solo")
                    except Exception as e:
                        logger.error("Failed to resolve turn for session %s: %s", session_id, e, exc_info=True)
                        snapshot = await adb(db.get_turn_snapshot, session_id)
                        reason = snapshot.get("fallback_reason") if snapshot else None
                        if reason == "models_unavailable":
                            msg = "⚠️ The generative models are currently overloaded or unavailable. Your action was saved. Please try again in a moment."
                        else:
                            msg = f"⚠️ The LLM failed to resolve this turn: {e}"
                        await interaction.followup.send(msg)
                        return

                    outcome = turn_response.outcome   # always a plain dict from TurnService
                    items_gained_by_user = turn_response.items_gained_by_user  # {user_id: [items]}
                    levels_gained = turn_response.levels_gained
                    xp_gained = turn_response.xp_gained
                    new_char = turn_response.new_char

                    scen_curr = turn_response.session.get("scenario", "fantasy")
                    loc_curr = outcome.get("location") or turn_response.session.get("current_location", "")

                    raw_next_choices, next_narrative, scene_title, partner_arg, npcs_arg = game_engine.extract_scene_fields(
                        outcome, session=turn_response.session
                    )
                    new_choices = self._clean_choices(
                        raw_next_choices, scenario=scen_curr, location=loc_curr, char=new_char,
                        dialogue_partner=partner_arg, current_npcs=npcs_arg, session_id=session_id
                    )
                    outcome["next_narrative"] = next_narrative
                    outcome["scene_title"] = scene_title

                    # Build new_history from TurnService's already-persisted history
                    new_history = list(turn_response.session.get("history", []))

                    if len(session["turn_order"]) > 1:
                        await adb(db.advance_turn, session_id)

                    await adb(db.save_session_scene, session_id, scene_title,
                                           next_narrative, new_choices, new_history,
                                           location=outcome.get("location"), nearby_enemies=outcome.get("nearby_enemies"),
                                           current_npcs=outcome.get("npcs_present", []),
                                           dialogue_partner=partner_arg)
                    merchant = _apply_merchant_encounter_result(session_id, outcome.get("merchant_encounter"))

                    result_display = session.get("result_display", "detailed")
                    result_summary = (f"**{action['stat']} check** ({action['check'].chance}% chance) "
                                      f"→ **{action['check'].tier_label}**")
                    loot_text = _format_items_gained(items_gained_by_user.get(user_id, []))


                    if new_char["hp"] <= 0:
                        embed = discord.Embed(
                            title="💀 The Party Has Fallen" if len(session["turn_order"]) > 1 else "💀 You have fallen",
                            description=outcome.get("outcome_narrative", "Darkness takes you."),
                            color=discord.Color.red())
                        embed.add_field(name="Result", value=result_summary)
                        if loot_text:
                            embed.add_field(name="🎒 Loot", value=loot_text, inline=False)
                        await adb(db.finish_session, session_id)
                        await self._safe_send(interaction, embed=embed)
                        return

                    outcome_embeds = build_outcome_embeds(
                        outcome=outcome,
                        check_field_name="🎯 Check",
                        check_field_value=result_summary,
                        loot_text=loot_text,
                        result_display=result_display,
                        xp_by_user={new_char["name"]: xp_gained},
                        session_id=session_id,
                        primary_tier=action["check"].tier,
                    )
                    await self._safe_send(interaction, embeds=outcome_embeds)

                    await self._announce_levelup(interaction, user_id, levels_gained)

                    fresh_session = await adb(db.get_session, session_id)
                    next_turn_uid = db.current_turn_user_id(fresh_session)
                    next_actor_char = await adb(db.get_character, next_turn_uid)
                    image_url = await self._maybe_generate_image(fresh_session, outcome.get("image_prompt"))

                    next_embeds = scene_embed(fresh_session, next_actor_char, outcome.get("scene_title"),
                                              outcome.get("next_narrative"), new_choices, image_url)
                    next_view = ChoiceView(self, session_id, next_turn_uid, new_choices, next_actor_char, merchant)
                    await self._safe_send(interaction, embeds=next_embeds, view=next_view)

            except LockAcquisitionError:
                try:
                    if not interaction.response.is_done():
                        await interaction.response.send_message('Still processing, hang on...', ephemeral=True)
                    else:
                        await interaction.followup.send('Still processing, hang on...', ephemeral=True)
                except:
                    pass

    async def handle_retry(self, interaction: discord.Interaction, session_id: int):
            try:
                async with distributed_session_lock(session_id, raise_http_error=False):
                    session = await adb(db.get_session, session_id)
                    if not session or session.get("status") != "active":
                        await interaction.followup.send("This adventure isn't active anymore.", ephemeral=True)
                        return
                
                    last_info = self._last_picks.get(session_id)
                    uid = last_info[0] if last_info else interaction.user.id
                
                    char = await adb(db.get_character, uid)
                    inv = await adb(db.get_inventory, uid)
                    party = [(char, inv)]
                    
                    try:
                        turn_response = await TurnService.retry_narration(session_id, uid)
                    except Exception as e:
                        await interaction.followup.send(f"The LLM failed to resolve this retry: {e}")
                        return

                    outcome = turn_response.outcome
                    action = turn_response.action
                    new_history = list(turn_response.session.get("history", []))

                    scen_curr = session.get("scenario", "fantasy")
                    loc_curr = outcome.get("location") or session.get("current_location", "")

                
                    raw_next_choices, next_narrative, scene_title, partner_arg, npcs_arg = game_engine.extract_scene_fields(
                        outcome, session=session
                    )
                    new_choices = self._clean_choices(
                        raw_next_choices, scenario=scen_curr, location=loc_curr, char=char,
                        dialogue_partner=partner_arg, current_npcs=npcs_arg, session_id=session_id
                    )
                    outcome["next_narrative"] = next_narrative
                    outcome["scene_title"] = scene_title
                
                    await adb(db.clear_pending_picks, session_id)
                    await adb(db.save_session_scene, session_id, scene_title,
                                           next_narrative, new_choices, new_history,
                                           location=outcome.get("location"), nearby_enemies=outcome.get("nearby_enemies"),
                                           current_npcs=outcome.get("npcs_present", []),
                                           dialogue_partner=partner_arg)
                    merchant = session.get("merchant", {}) # Don't re-apply merchant state
                    items_gained_by_user = {}
                    loot_text = ""

                    hp_checks = [await adb(db.get_character, uid)]
                    all_down = all(c["hp"] <= 0 for c in hp_checks)
                    
                    summaries = []
                    chk = action.get('check', {})
                    if not isinstance(chk, dict):
                        chk = {"chance": getattr(chk, "chance", 100), "tier_label": getattr(chk, "tier_label", "Action"), "tier": getattr(chk, "tier", "success")}
                    chance_val = chk.get('chance', 100)
                    tier_label = chk.get('tier_label', 'Action')
                    
                    line = (f"**{action.get('char', {}).get('name', 'Hero')}** \U0001f3af {action.get('stat', 'NONE')} check "
                            f"({chance_val}%) \u2192 **{tier_label}**")
                    summaries.append(line)

                    if all_down:
                        embed = discord.Embed(title="\U0001f480 The Party Has Fallen",
                                               description=outcome.get("outcome_narrative", "Darkness takes you."),
                                               color=discord.Color.red())
                        embed.add_field(name="Results", value="\n\n".join(summaries))
                        await adb(db.finish_session, session_id)
                        await self._safe_send(interaction, embed=embed)
                        return

                    primary_tier = chk.get('tier', 'success')
                
                    outcome_embeds = build_outcome_embeds(
                        outcome=outcome,
                        check_field_name="\U0001f3af Checks",
                        check_field_value="\n\n".join(summaries),
                        loot_text=loot_text,
                        result_display=session.get("result_display", "detailed"),
                        xp_by_user={},
                        session_id=session_id,
                        primary_tier=primary_tier,
                    )
                    await self._safe_send(interaction, embeds=outcome_embeds)
                    
                    levels_gained = []

                    if levels_gained:
                        await self._announce_levelup(interaction, uid, levels_gained)

                    fresh_session = await adb(db.get_session, session_id)
                    image_url = await self._maybe_generate_image(fresh_session, outcome.get("image_prompt"))

                    # Reconstruct view and sync embeds
                    if fresh_session["mode"] == "sync":
                        next_embeds = sync_scene_embed(fresh_session, party, outcome.get("scene_title"),
                                                       outcome.get("next_narrative"), new_choices, waiting_on=[],
                                                       image_url=image_url)
                        next_view = SyncChoiceView(self, session_id, [uid], new_choices, party, merchant)
                    else:
                        next_embeds = scene_embed(fresh_session, char, outcome.get("scene_title"),
                                                  outcome.get("next_narrative"), new_choices, image_url)
                        next_view = ChoiceView(self, session_id, uid, new_choices, char, merchant)
                    
                    await self._safe_send(interaction, embeds=next_embeds, view=next_view)

            except LockAcquisitionError:
                try:
                    if not interaction.response.is_done():
                        await interaction.response.send_message('Still processing, hang on...', ephemeral=True)
                    else:
                        await interaction.followup.send('Still processing, hang on...', ephemeral=True)
                except:
                    pass

    async def handle_sync_pick(self, interaction: discord.Interaction, session_id: int,
                               choice_index: int | None = None, custom_text: str | None = None,
                               direct_choice: dict | None = None,
                               is_item_action: bool = False, item_name: str | None = None, target_name: str | None = None):
            user_id = interaction.user.id
            session = await adb(db.get_session, session_id)
            if not session or session["status"] != "active":
                msg = "This adventure isn't active anymore."
                if interaction.response.is_done():
                    await interaction.followup.send(msg, ephemeral=True)
                else:
                    await interaction.response.send_message(msg, ephemeral=True)
                return
            if session.get("merchant", {}).get("active"):
                msg = "🛍️ The party is currently browsing the merchant's stall! Finish or leave the shop before continuing the adventure."
                if interaction.response.is_done():
                    await interaction.followup.send(msg, ephemeral=True)
                else:
                    await interaction.response.send_message(msg, ephemeral=True)
                return
            member_ids = session["turn_order"]
            if user_id not in member_ids:
                msg = "You're not part of this adventure."
                if interaction.response.is_done():
                    await interaction.followup.send(msg, ephemeral=True)
                else:
                    await interaction.response.send_message(msg, ephemeral=True)
                return
            if str(user_id) in session["pending_picks"]:
                msg = "You've already locked in your action this round."
                if interaction.response.is_done():
                    await interaction.followup.send(msg, ephemeral=True)
                else:
                    await interaction.response.send_message(msg, ephemeral=True)
                return

            if is_item_action:
                pick = {
                    "is_item_action": True,
                    "item_name": item_name,
                    "target_name": target_name,
                    "custom_text": custom_text or f"Use {item_name} on {target_name}"
                }
            elif direct_choice is not None:
                pick = {"direct_choice": direct_choice}
            elif choice_index is not None:
                pick = {"choice_index": choice_index}
            else:
                pick = {"custom_text": custom_text}

            await adb(db.set_pending_pick, session_id, user_id, pick)
            session = await adb(db.get_session, session_id)
            waiting_on = [uid for uid in member_ids if str(uid) not in session["pending_picks"]]

            if waiting_on:
                mentions = ", ".join(f"<@{uid}>" for uid in waiting_on)
                msg = f"✅ Action locked in! Waiting on {mentions}..."
                if interaction.response.is_done():
                    await interaction.followup.send(msg, ephemeral=True)
                else:
                    await interaction.response.send_message(msg, ephemeral=True)
                return

            if not interaction.response.is_done():
                try:
                    await interaction.response.defer()
                except (discord.NotFound, discord.HTTPException):
                    pass

            await self._check_party_ready_and_resolve(session_id, interaction)

    async def _check_party_ready_and_resolve(self, session_id: int, interaction: discord.Interaction):
            try:
                async with distributed_session_lock(session_id, raise_http_error=False):
                    session = await adb(db.get_session, session_id)
                    picks = session["pending_picks"]
                    member_ids = session["turn_order"]

                    try:
                        actions = [await self._resolve_pick(session, uid, picks[str(uid)]) for uid in member_ids]
                    except Exception as e:
                        await adb(db.clear_pending_picks, session_id)
                        await interaction.followup.send(f"⚠️ The LLM failed to interpret an action: {e}")
                        return

                    party = list(await asyncio.gather(
                        *[(asyncio.gather(adb(db.get_character, uid), adb(db.get_inventory, uid)))
                          for uid in member_ids]
                    ))
                    try:
                        outcome = await game_engine.resolve_turn(session, party, actions)
                    except Exception as e:
                        await adb(db.clear_pending_picks, session_id)
                        await interaction.followup.send(f"⚠️ The LLM failed to resolve this round: {e}")
                        return

                    mp_already_spent = {a["char"]["user_id"]: a["mp_spent"] for a in actions}
                    items_gained_by_user = game_engine.apply_outcome(session_id, party, outcome, mp_already_spent, actions=actions)
                    try:
                        game_engine.apply_quest_update(session_id, outcome)
                    except Exception as e:
                        logger.warning("apply_quest_update failed during party sync (non-fatal): %s", e)

                    summaries, all_levels = [], []
                    xp_by_name = {}
                    for uid, action in zip(member_ids, actions):
                        bonus_xp = 0
                        for co in outcome.get("character_outcomes", []):
                            if isinstance(co, dict) and co.get("name", "").lower() == action["char"]["name"].lower():
                                bonus_xp = _safe_int(co.get("xp_change"), default=0)
                                break
                        
                        levels_gained = self._apply_xp(uid, action["check"])
                        if bonus_xp > 0:
                            bonus_levels = await adb(db.add_xp, uid, bonus_xp)
                            levels_gained.extend(bonus_levels)
                    
                        xp_by_name[action["char"]["name"]] = XP_REWARDS.get(action["check"].tier, 0) + bonus_xp
                        line = (f"**{action['char']['name']}** — {action['stat']} check "
                                f"({action['check'].chance}%) → **{action['check'].tier_label}**")
                        summaries.append(line)
                        if levels_gained:
                            all_levels.append((uid, levels_gained))

                    scen_curr = session.get("scenario", "fantasy")
                    loc_curr = outcome.get("location") or session.get("current_location", "")
                    first_char = party[0][0] if party and party[0] else None

                    history_entry = "; ".join(
                        f"[{a['check'].tier_label}] {a['char']['name']}: {a['label']}" for a in actions)
                    outcome_nar = outcome.get("outcome_narrative", "")
                    history_entry += f" -> {self._compact_summary(outcome_nar, max_chars=500)}"
            
                    from mechanics.world.mobility import get_session_dialogue_partners; has_partner = bool(get_session_dialogue_partners(outcome))
                    dyn_limit = 12 if has_partner else 4
                    new_history = game_engine.push_history(session["history"], history_entry, limit=dyn_limit)

                    raw_next_choices, next_narrative, scene_title, partner_arg, npcs_arg = game_engine.extract_scene_fields(
                        outcome, session=session
                    )
                    new_choices = self._clean_choices(
                        raw_next_choices, scenario=scen_curr, location=loc_curr, char=first_char,
                        dialogue_partner=partner_arg, current_npcs=npcs_arg, session_id=session_id
                    )
                    outcome["next_narrative"] = next_narrative
                    outcome["scene_title"] = scene_title

                    await adb(db.clear_pending_picks, session_id)
                    await adb(db.save_session_scene, session_id, scene_title,
                                           next_narrative, new_choices, new_history,
                                           location=outcome.get("location"), nearby_enemies=outcome.get("nearby_enemies"),
                                           current_npcs=outcome.get("npcs_present", []),
                                           dialogue_partner=partner_arg)
                    merchant = _apply_merchant_encounter_result(session_id, outcome.get("merchant_encounter"))

                    loot_text = _format_items_gained_multi(items_gained_by_user, party)

                    result_display = session.get("result_display", "detailed")
                    # Fetch all chars concurrently to check hp
                    hp_checks = await asyncio.gather(*[adb(db.get_character, uid) for uid in member_ids])
                    all_down = all(c["hp"] <= 0 for c in hp_checks)
                    if all_down:
                        embed = discord.Embed(title="💀 The Party Has Fallen",
                                               description=outcome.get("outcome_narrative", "Darkness takes you."),
                                               color=discord.Color.red())
                        embed.add_field(name="Results", value="\n\n".join(summaries))
                        if loot_text:
                            embed.add_field(name="🎒 Loot", value=loot_text, inline=False)
                        await adb(db.finish_session, session_id)
                        await self._safe_send(interaction, embed=embed)
                        return

                    # Dominant tier = worst individual result (drives embed colour)
                    tier_rank = {"crit_fail": 0, "fail": 1, "success": 2, "crit_success": 3}
                    primary_tier = min(
                        (a["check"].tier for a in actions),
                        key=lambda t: tier_rank.get(t, 2)
                    )
                    outcome_embeds = build_outcome_embeds(
                        outcome=outcome,
                        check_field_name="🎯 Checks",
                        check_field_value="\n\n".join(summaries),
                        loot_text=loot_text,
                        result_display=result_display,
                        xp_by_user=xp_by_name,
                        session_id=session_id,
                        primary_tier=primary_tier,
                    )
                    await self._safe_send(interaction, embeds=outcome_embeds)

                    for uid, _ in all_levels:
                        await self._announce_levelup(interaction, uid, dict(all_levels)[uid])

                    fresh_session = await adb(db.get_session, session_id)
                    fresh_party = list(await asyncio.gather(
                        *[(asyncio.gather(adb(db.get_character, uid), adb(db.get_inventory, uid)))
                          for uid in member_ids]
                    ))
                    image_url = await self._maybe_generate_image(fresh_session, outcome.get("image_prompt"))

                    next_embeds = sync_scene_embed(fresh_session, fresh_party, outcome.get("scene_title"),
                                                   outcome.get("next_narrative"), new_choices, waiting_on=[],
                                                   image_url=image_url)
                    next_view = SyncChoiceView(self, session_id, member_ids, new_choices, fresh_party, merchant)
                    await self._safe_send(interaction, embeds=next_embeds, view=next_view)

            except LockAcquisitionError:
                try:
                    if not interaction.response.is_done():
                        await interaction.response.send_message('Still processing, hang on...', ephemeral=True)
                    else:
                        await interaction.followup.send('Still processing, hang on...', ephemeral=True)
                except:
                    pass

