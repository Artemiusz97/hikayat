import discord
import asyncio
import db
import game_engine
from services.turn_service import TurnService
from .embeds import *
from .views.choices import ChoiceView, SyncChoiceView
from .embeds import _apply_merchant_encounter_result, _format_items_gained, _format_items_gained_multi, _is_dialogue_partner, _safe_int, _get_choice_skill_emoji
from mechanics.system.concurrency import distributed_session_lock, LockAcquisitionError
import logging
logger = logging.getLogger(__name__)

class GameLoopMixin:
    async def _resolve_pick(self, session: dict, user_id: int, pick: dict) -> dict:
        """Turns a recorded pick (choice_index, direct_choice, or custom_text) into an
        action dict via TurnService.prepare_and_roll_action."""
        return await TurnService.prepare_and_roll_action(
            session_id=session["id"],
            user_id=user_id,
            raw_pick=pick,
            session=session,
            enforce_explicit_mp=False,
        )

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
                    if isinstance(outcome, dict) and outcome.get("_hybrid_choices_built") and raw_next_choices:
                        new_choices = list(raw_next_choices)
                    else:
                        new_choices = self._clean_choices(
                            raw_next_choices, scenario=scen_curr, location=loc_curr, char=new_char,
                            dialogue_partner=partner_arg, current_npcs=npcs_arg, session_id=session_id,
                            departed_npcs=outcome.get("departed_characters") or outcome.get("departed_npcs"),
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
                                           dialogue_partner=partner_arg,
                                           current_node_id=outcome.get("current_node_id"),
                                           focal_point=outcome.get("focal_point"))
                    merchant = _apply_merchant_encounter_result(session_id, outcome.get("merchant_encounter"))

                    result_display = session.get("result_display", "detailed")
                    is_free_action = (
                        str(action.get("stat") or "").upper() in ("NONE", "FREE", "ITEM", "")
                        or (getattr(action.get("check"), "chance", 100) == 100 and str(action.get("stat") or "").upper() in ("NONE", "FREE", "ITEM", "None"))
                    )
                    if is_free_action:
                        emoji = _get_choice_skill_emoji(action)
                        check_field_name = f"{emoji} Action"
                        result_summary = f"*{action.get('label', 'Action')}*"
                        primary_tier = "free"
                    else:
                        check_field_name = "🎯 Check"
                        result_summary = (f"**{action['stat']} check** ({action['check'].chance}% chance) "
                                          f"→ **{action['check'].tier_label}**")
                        primary_tier = action["check"].tier
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
                        check_field_name=check_field_name,
                        check_field_value=result_summary,
                        loot_text=loot_text,
                        result_display=result_display,
                        xp_by_user={new_char["name"]: xp_gained},
                        session_id=session_id,
                        primary_tier=primary_tier,
                    )
                    await self._safe_send(interaction, embeds=outcome_embeds)

                    await self._announce_levelup(interaction, user_id, levels_gained)

                    fresh_session = await adb(db.get_session, session_id)
                    next_turn_uid = db.current_turn_user_id(fresh_session)
                    next_actor_char = await adb(db.get_character, next_turn_uid)
                    image_url = await self._maybe_generate_image(fresh_session, outcome.get("image_prompt"), outcome=outcome)

                    next_embeds = scene_embed(fresh_session, next_actor_char, outcome.get("scene_title"),
                                              outcome.get("next_narrative"), new_choices, image_url)
                    next_view = ChoiceView(self, session_id, next_turn_uid, new_choices, next_actor_char, merchant)
                    _, discord_file = prepare_discord_image(image_url)
                    send_kwargs = {"embeds": next_embeds, "view": next_view}
                    if discord_file:
                        send_kwargs["file"] = discord_file
                    await self._safe_send(interaction, **send_kwargs)

            except LockAcquisitionError:
                try:
                    if not interaction.response.is_done():
                        await interaction.response.send_message('Still processing, hang on...', ephemeral=True)
                    else:
                        await interaction.followup.send('Still processing, hang on...', ephemeral=True)
                except:
                    pass

    async def handle_retry(self, interaction: discord.Interaction, session_id: int):
            if not interaction.response.is_done():
                try:
                    await interaction.response.defer()
                except (discord.NotFound, discord.HTTPException):
                    pass
            try:
                async with distributed_session_lock(session_id, raise_http_error=False):
                    session = await adb(db.get_session, session_id)
                    if not session or session.get("status") != "active":
                        await self._safe_send(interaction, content="This adventure isn't active anymore.", ephemeral=True)
                        return
                
                    last_info = self._last_picks.get(session_id)
                    uid = last_info[0] if last_info else interaction.user.id
                
                    char = await adb(db.get_character, uid)
                    inv = await adb(db.get_inventory, uid)
                    party = [(char, inv)]
                    
                    history = session.get("history") or []

                    # If Turn 0 (opening scene, no action history yet), regenerate opening scene
                    if not history:
                        await self.launch_opening_scene(interaction, session, use_followup=True)
                        return

                    try:
                        turn_response = await TurnService.retry_narration(session_id, uid)
                    except ValueError as ve:
                        if "No completed snapshot available to retry" in str(ve):
                            await self._safe_send(interaction, content="⚠️ No completed turn snapshot available to retry.")
                        else:
                            await self._safe_send(interaction, content=f"⚠️ The LLM failed to resolve this retry: {ve}")
                        return
                    except Exception as e:
                        logger.error("Failed to retry narration for session %s: %s", session_id, e, exc_info=True)
                        await self._safe_send(interaction, content=f"⚠️ The LLM failed to resolve this retry: {e}")
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
                        dialogue_partner=partner_arg, current_npcs=npcs_arg, session_id=session_id,
                        departed_npcs=outcome.get("departed_characters") or outcome.get("departed_npcs"),
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
                    
                    is_free_action = (
                        str(action.get("stat") or "").upper() in ("NONE", "FREE", "ITEM", "")
                        or (chance_val == 100 and str(action.get("stat") or "").upper() in ("NONE", "FREE", "ITEM", "None"))
                    )
                    if is_free_action:
                        emoji = _get_choice_skill_emoji(action)
                        line = f"**{action.get('char', {}).get('name', 'Hero')}** {emoji} *{action.get('label', 'Action')}*"
                        primary_tier = "free"
                        check_field_name = f"{emoji} Action"
                    else:
                        line = (f"**{action.get('char', {}).get('name', 'Hero')}** \U0001f3af {action.get('stat', 'NONE')} check "
                                f"({chance_val}%) \u2192 **{tier_label}**")
                        primary_tier = chk.get('tier', 'success')
                        check_field_name = "\U0001f3af Checks"
                    summaries.append(line)

                    if all_down:
                        embed = discord.Embed(title="\U0001f480 The Party Has Fallen",
                                               description=outcome.get("outcome_narrative", "Darkness takes you."),
                                               color=discord.Color.red())
                        embed.add_field(name="Results", value="\n\n".join(summaries))
                        await adb(db.finish_session, session_id)
                        await self._safe_send(interaction, embed=embed)
                        return
                
                    outcome_embeds = build_outcome_embeds(
                        outcome=outcome,
                        check_field_name=check_field_name,
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
                    image_url = await self._maybe_generate_image(fresh_session, outcome.get("image_prompt"), outcome=outcome)

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
                    
                    _, discord_file = prepare_discord_image(image_url)
                    send_kwargs = {"embeds": next_embeds, "view": next_view}
                    if discord_file:
                        send_kwargs["file"] = discord_file
                    await self._safe_send(interaction, **send_kwargs)

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

            try:
                resolved_pick = await self._resolve_pick(session, user_id, pick)
                chk = resolved_pick.get("check")
                if chk is not None and not isinstance(chk, dict):
                    resolved_pick = dict(resolved_pick)
                    resolved_pick["check"] = {
                        "chance": getattr(chk, "chance", 100),
                        "roll": getattr(chk, "roll", 100.0),
                        "tier": getattr(chk, "tier", "success"),
                        "tier_label": getattr(chk, "tier_label", "Success"),
                        "succeeded": getattr(chk, "succeeded", True),
                        "requirement": getattr(chk, "requirement", resolved_pick.get("requirement", 0)),
                    }
                pick_to_store = resolved_pick
            except Exception:
                pick_to_store = pick

            await adb(db.set_pending_pick, session_id, user_id, pick_to_store)
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
                        is_free = (
                            str(action.get("stat") or "").upper() in ("NONE", "FREE", "ITEM", "")
                            or (action["check"].chance == 100 and str(action.get("stat") or "").upper() in ("NONE", "FREE", "ITEM", "None"))
                        )
                        if is_free:
                            emoji = _get_choice_skill_emoji(action)
                            line = f"**{action['char']['name']}** {emoji} *{action.get('label', 'Action')}*"
                        else:
                            line = (f"**{action['char']['name']}** — {action['stat']} check "
                                    f"({action['check'].chance}%) → **{action['check'].tier_label}**")
                        summaries.append(line)
                        if levels_gained:
                            all_levels.append((uid, levels_gained))

                    scen_curr = session.get("scenario", "fantasy")
                    loc_curr = outcome.get("location") or session.get("current_location", "")
                    first_char = party[0][0] if party and party[0] else None

                    action_summary_str = "; ".join(
                        f"[{a['check'].tier_label}] {a['char']['name']}: {a['label']}" for a in actions
                    )
                    outcome_nar = outcome.get("outcome_narrative", "")
                    next_nar_hist = outcome.get("next_narrative") or outcome.get("narrative") or ""
                    history_entry = {
                        "action": action_summary_str,
                        "outcome": outcome_nar,
                        "next": next_nar_hist,
                        "summary": f"{action_summary_str} -> {self._compact_summary(outcome_nar, max_chars=500)}",
                    }
            
                    from mechanics.world.mobility import get_session_dialogue_partners; has_partner = bool(get_session_dialogue_partners(outcome))
                    dyn_limit = 12 if has_partner else 4
                    new_history = game_engine.push_history(session["history"], history_entry, limit=dyn_limit)

                    raw_next_choices, next_narrative, scene_title, partner_arg, npcs_arg = game_engine.extract_scene_fields(
                        outcome, session=session
                    )
                    if isinstance(outcome, dict) and outcome.get("_hybrid_choices_built") and raw_next_choices:
                        new_choices = list(raw_next_choices)
                    else:
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
                    tier_rank = {"crit_fail": 0, "fail": 1, "free": 2, "success": 3, "crit_success": 4}
                    all_free = all(
                        str(a.get("stat") or "").upper() in ("NONE", "FREE", "ITEM", "")
                        or (a["check"].chance == 100 and str(a.get("stat") or "").upper() in ("NONE", "FREE", "ITEM", "None"))
                        for a in actions
                    )
                    if all_free:
                        primary_tier = "free"
                        check_field_name = "💬 Actions"
                    else:
                        primary_tier = min(
                            (a["check"].tier for a in actions),
                            key=lambda t: tier_rank.get(t, 3)
                        )
                        check_field_name = "🎯 Checks"
                    outcome_embeds = build_outcome_embeds(
                        outcome=outcome,
                        check_field_name=check_field_name,
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
                    image_url = await self._maybe_generate_image(fresh_session, outcome.get("image_prompt"), outcome=outcome)

                    next_embeds = sync_scene_embed(fresh_session, fresh_party, outcome.get("scene_title"),
                                                   outcome.get("next_narrative"), new_choices, waiting_on=[],
                                                   image_url=image_url)
                    next_view = SyncChoiceView(self, session_id, member_ids, new_choices, fresh_party, merchant)
                    _, discord_file = prepare_discord_image(image_url)
                    send_kwargs = {"embeds": next_embeds, "view": next_view}
                    if discord_file:
                        send_kwargs["file"] = discord_file
                    await self._safe_send(interaction, **send_kwargs)

            except LockAcquisitionError:
                try:
                    if not interaction.response.is_done():
                        await interaction.response.send_message('Still processing, hang on...', ephemeral=True)
                    else:
                        await interaction.followup.send('Still processing, hang on...', ephemeral=True)
                except:
                    pass

