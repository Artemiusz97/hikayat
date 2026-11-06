import asyncio
import logging
import discord
import db
from db import adb

logger = logging.getLogger(__name__)


class FactionMixin:
    """Faction HQ menu, membership application, safehouse rest, quartermaster, bounty, and promotion trial handlers for AdventureCog."""

    async def open_faction_hq_menu(self, interaction: discord.Interaction, session_id: int, user_id: int):
        session = db.get_session(session_id)
        current_loc = session.get("current_location", "")
        faction = db.get_faction_by_hq(session_id, current_loc)
        if not faction:
            await interaction.response.send_message("No Faction HQ here.", ephemeral=True)
            return
        
        from mechanics.social.factions import FactionHQView
        view = FactionHQView(self, session_id, session["turn_order"], faction)
        embed = discord.Embed(title=f"🏛️ {faction.get('name', 'HQ')} Headquarters",
                              description=faction.get("notes", "A bustling center of faction activity."),
                              color=discord.Color.blurple())
        
        char = db.get_character(user_id)
        rep = faction.get("reputation_score", 0)
        from mechanics.social.factions import get_faction_tier
        tier = get_faction_tier(rep)
        
        embed.add_field(name="Your Standing", value=f"**{tier['name']}** ({rep:+d})", inline=True)
        if char.get("joined_faction_id") == faction["faction_id"]:
            embed.add_field(name="Your Rank", value=f"Rank {char.get('faction_rank', 1)}: {char.get('faction_title', 'Member')}", inline=True)
        else:
            embed.add_field(name="Membership", value="Not a member", inline=True)
            
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def faction_apply(self, interaction: discord.Interaction, session_id: int, user_id: int, faction: dict):
        import scenario_data

        session = (await adb(db.get_session, session_id)) or {}
        if scenario_data.is_anomalous_incursions_scenario(session.get("scenario", "")):
            from mechanics.social.factions import infer_anomalous_faction_archetype, join_or_transfer_anomalous_faction

            target_fac = (
                infer_anomalous_faction_archetype(faction)
                or faction.get("faction_id")
                or faction.get("name", "")
            )
            res = await adb(join_or_transfer_anomalous_faction, session_id, target_fac, user_id)
            if not res.get("success"):
                await interaction.response.send_message(
                    res.get("error") or "Unable to enlist in this faction.",
                    ephemeral=True,
                )
                return
            await interaction.response.send_message(
                res.get("message") or f"Welcome to **{faction.get('name', 'the faction')}**!",
                ephemeral=True,
            )
            return

        char = await adb(db.get_character, user_id)
        if char.get("joined_faction_id"):
            await interaction.response.send_message("You are already pledged to a faction! Defecting carries severe penalties.", ephemeral=True)
            return
            
        # Join faction logic
        await adb(db.set_character_faction_membership, char["id"], faction["faction_id"], 1, "Initiate")
        await interaction.response.send_message(f"Welcome to **{faction.get('name', 'the faction')}**! You are now a member.", ephemeral=True)

    async def faction_rest(self, interaction: discord.Interaction, session_id: int, user_id: int, faction: dict):
        rep = faction.get("reputation_score", 0)
        from mechanics.social.factions import get_faction_tier
        tier = get_faction_tier(rep)
        if tier["tier_level"] < 2:
            await interaction.response.send_message("You need **Liked** standing or higher to use the safehouse rest.", ephemeral=True)
            return
            
        char = db.get_character(user_id)
        db.apply_hp_mp_delta(user_id, char["max_hp"], char["max_mp"], 0)
        await interaction.response.send_message("You rest at the faction safehouse, recovering all HP and MP safely.", ephemeral=True)

    async def faction_quartermaster(self, interaction: discord.Interaction, session_id: int, user_id: int, faction: dict):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        
        session = await adb(db.get_session, session_id)
        current_day, current_minute, _ = await adb(db.get_session_time, session_id)
        merchant = session.setdefault("merchant", {})
        faction_id = faction.get("faction_id") or faction.get("id") or faction.get("name", "default")
        faction_key = f"faction_{faction_id}"

        from mechanics.combat.merchant import (
            generate_faction_quartermaster_shop,
            BuySelectView,
            get_or_create_merchant_catalogue,
            update_merchant_catalogue,
            compute_effective_shop_item_price,
            get_anomalous_shop_faction_context,
        )

        cat_entry, needs_restock = get_or_create_merchant_catalogue(
            merchant, faction_key, current_day, current_minute
        )
        if needs_restock:
            shop = await generate_faction_quartermaster_shop(faction, session)
            cat_entry = update_merchant_catalogue(merchant, faction_key, shop, current_day, current_minute)

        discount = cat_entry.get("discount_pct", 0)
        merchant.update({
            "active": True,
            "active_store_key": faction_key,
            "stock": cat_entry["stock"],
            "discount_pct": discount,
            "is_faction_quartermaster": True,
            "quartermaster_faction_arch": faction.get("archetype_key") or faction.get("category") or "",
            "restock_day": cat_entry.get("restock_day", current_day),
            "restock_minute": cat_entry.get("restock_minute", current_minute),
        })
        await adb(db.save_merchant_state, session_id, merchant)

        stock = [item for item in cat_entry.get("stock", []) if item.get("quantity", 0) > 0]
        if not stock:
            await interaction.followup.send(
                f"📦 The quartermaster's stock is sold out for today. Wares will restock on **Day {current_day + 1}**!",
                ephemeral=True
            )
            return

        shop_ctx = await adb(
            get_anomalous_shop_faction_context,
            session,
            session.get("current_location", ""),
            False,
            user_id,
        )
        view = BuySelectView(self, session_id, stock, discount, shop_ctx=shop_ctx)
        lines = "\n".join(
            f"**{i['name']}** ({i['item_type']}) — {compute_effective_shop_item_price(i, shop_ctx=shop_ctx, discount_pct=discount)}g "
            f"x{i['quantity']}\n{i.get('description') or ''}".rstrip()
            for i in stock)

        intro = cat_entry.get("intro_narrative") or "Exclusive wares available for faction operatives."
        embed = discord.Embed(title="🛍️ Faction Quartermaster", description=intro, color=discord.Color.dark_gold())
        embed.add_field(name="Discount", value=f"{discount}% off", inline=False)
        embed.set_footer(text=f"🕒 Daily Restock: Start of Day {current_day + 1}")
        content = f"**For sale:**\n{lines}"
        if len(content) > 1950:
            content = content[:1920] + "\n\n*(additional items available in dropdown below)*"
        await interaction.followup.send(content=content, embed=embed, view=view, ephemeral=True)

    async def faction_bounty(self, interaction: discord.Interaction, session_id: int, user_id: int, faction: dict):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
            
        session = await adb(db.get_session, session_id)
        from mechanics.narrative.bounty import generate_faction_bounty_board, get_faction_rep_reward_from_quest
        from cogs.adventure.views.quests import BountyBoardView
        bounties = await generate_faction_bounty_board(session, faction, force_refresh=False)
        
        if not bounties:
            await interaction.followup.send("No faction bounties are currently available.", ephemeral=True)
            return
            
        embed = discord.Embed(title="📋 Faction Bounty Board", description="Exclusive tasks for members.", color=discord.Color.dark_red())
        for b in bounties[:25]:
            rep_reward = get_faction_rep_reward_from_quest(b)
            req = f"{b['reward_xp']} XP | {b['reward_gold']} Gold | +{rep_reward} Faction Rep"
            if b.get("reward_item"):
                req += f" | {b['reward_item']}"
            f_name = f"[{b['status']}] {b['title']}"[:250]
            f_val = f"{b['objective']}\n**Reward:** {req}"[:1020]
            embed.add_field(name=f_name, value=f_val, inline=False)
            
        avail_bounties = [b for b in bounties if b.get("status") == "Available"]
        view = BountyBoardView(session, avail_bounties) if session else None
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    async def faction_calibrate(
        self,
        interaction: discord.Interaction,
        session_id: int,
        user_id: int,
        faction_id: str,
        attribute: str,
        combat_archetype: str,
        ability_medium: str,
    ):
        from api.codex_phone import faction_hq_action
        from api.deps import FactionHQActionRequest
        from fastapi import HTTPException

        if not interaction.response.is_done():
            await interaction.response.defer()
        try:
            res = await faction_hq_action(
                session_id,
                FactionHQActionRequest(
                    user_id=user_id,
                    faction_id=faction_id,
                    action="calibrate",
                    attribute=attribute,
                    combat_archetype=combat_archetype,
                    ability_medium=ability_medium,
                ),
            )
            await interaction.edit_original_response(
                content=f"🧬 **Telemetry Calibration Complete!** {res.get('message', '')}",
                view=None,
            )
        except HTTPException as exc:
            await interaction.edit_original_response(content=f"❌ Calibration denied: {exc.detail}", view=None)

    async def faction_promotion(self, interaction: discord.Interaction, session_id: int, user_id: int, faction: dict):
        import scenario_data

        session = (await adb(db.get_session, session_id)) or {}
        if scenario_data.is_anomalous_incursions_scenario(session.get("scenario", "")):
            from mechanics.social.factions import get_anomalous_faction_state

            a_state = await adb(get_anomalous_faction_state, session_id, user_id)
            tier = int(a_state.get("promotion_tier", 0) or 0)
            title = a_state.get("promotion_title") or "Independent Freelancer"
            rep = int(a_state.get("promotion_rep", 0) or 0)
            if a_state.get("faction_archetype_key") == "freelancer" or tier <= 0:
                await interaction.response.send_message(
                    "Independent Freelancers do not hold agency rank. Enlist at a joinable Faction HQ first!",
                    ephemeral=True,
                )
                return
            await interaction.response.send_message(
                f"🎖️ **Agent Promotion Meter**: **Tier {tier} — {title}** ({rep}/100 Rep).\n"
                "Promotions in Anomalous Incursions advance automatically at **20 / 45 / 70 / 90 Rep** by completing Daily Mandatory Dispatches and Agency Bounties (no duel trials required).",
                ephemeral=True,
            )
            return

        char = await adb(db.get_character, user_id)
        rep = faction.get("reputation_score", 0)
        from mechanics.social.factions import get_eligible_rank, get_hierarchy, get_rank_title, get_incumbent_at_rank, get_promotion_trial_directive
        
        template = faction.get("hierarchy_template", "default")
        eligible = get_eligible_rank(template, rep)
        current_rank = char.get("faction_rank", 1)
        
        if eligible <= current_rank:
            await interaction.response.send_message("You don't have enough reputation to challenge for the next rank yet.", ephemeral=True)
            return
            
        target_rank = current_rank + 1
        roster = faction.get("leadership_roster", [])
        incumbent_name = get_incumbent_at_rank(roster, target_rank)
        
        if not incumbent_name:
            # Slot is vacant or already held by a player (edge case), auto-promote
            new_title = get_rank_title(template, target_rank)
            from mechanics.social.factions import promote_player_in_roster
            new_roster = promote_player_in_roster(roster, char["name"], target_rank, template)
            db.update_faction_leadership_roster(session_id, faction["faction_id"], new_roster)
            db.set_character_faction_membership(char["id"], faction["faction_id"], target_rank, new_title)
            await interaction.response.send_message(f"You have been promoted to **{new_title}**!", ephemeral=True)
            return
            
        # Store pending promotion in session so game_engine can resolve it
        session = db.get_session(session_id)
        scen_key = session.get("scenario", "fantasy")
        session["pending_promotion"] = {
            "faction_id": faction["faction_id"],
            "target_rank": target_rank,
            "player_name": char["name"],
            "template": template
        }
        db.update_session(session_id, extra={"pending_promotion": session["pending_promotion"]})
        
        # Inject the promotion trial directive into the current turn
        directive = get_promotion_trial_directive(current_rank, target_rank, incumbent_name, faction.get("name", "Faction"), template, scen_key)
        
        embed = discord.Embed(title="⚔️ Promotion Trial Triggered", description=f"You have challenged **{incumbent_name}** for the rank of {get_rank_title(template, target_rank)}! Wait for the GM to respond.", color=discord.Color.red())
        await interaction.response.send_message(embed=embed, ephemeral=False)
        
        # We manually trigger an LLM turn to resolve the challenge setup
        await self._trigger_promotion_trial_turn(interaction, session_id, directive)
        
    async def _trigger_promotion_trial_turn(self, interaction: discord.Interaction, session_id: int, directive: str):
        # We simulate a turn submission with the directive embedded in the narrative
        session = db.get_session(session_id)
        actor_char = db.get_character(interaction.user.id)
        party = [(db.get_character(uid), db.get_inventory(uid)) for uid in session["turn_order"]]
        
        async def background_task():
            from services.turn_service import TurnService
            user_action = f"Player initiates promotion trial:\n\n{directive}"

            if not interaction.channel:
                return
            await interaction.channel.send("*(The GM is setting up the promotion trial...)*")
            try:
                action = await TurnService.prepare_and_roll_action(
                    session_id=session_id,
                    user_id=interaction.user.id,
                    raw_pick={"direct_choice": {"label": user_action, "stat": "NONE", "requirement": 0, "mp_cost": 0}},
                    session=session,
                    char=dict(actor_char) if actor_char else None,
                    enforce_explicit_mp=False,
                )
                turn_res = await TurnService.resolve_action(session_id, interaction.user.id, action, mode="solo")
                outcome = turn_res.outcome
                
                # Render next turn
                from .embeds import sync_scene_embed, scene_embed
                updated_session = db.get_session(session_id)
                updated_party = [(db.get_character(uid), db.get_inventory(uid)) for uid in updated_session["turn_order"]]
                
                from cogs.adventure import SyncChoiceView, ChoiceView
                if updated_session["mode"] == "sync":
                    embeds = sync_scene_embed(updated_session, updated_party, updated_session["scene_title"], updated_session["narrative"], updated_session["choices"], updated_session["turn_order"])
                    view = SyncChoiceView(self, session_id, updated_session["turn_order"], updated_session["choices"], updated_party, updated_session["merchant"])
                else:
                    turn_uid = db.current_turn_user_id(updated_session)
                    turn_char = db.get_character(turn_uid)
                    embeds = scene_embed(updated_session, turn_char, updated_session["scene_title"], updated_session["narrative"], updated_session["choices"])
                    view = ChoiceView(self, session_id, turn_uid, updated_session["choices"], turn_char, updated_session["merchant"])
                    
                await interaction.channel.send(embeds=embeds, view=view)
                
            except Exception as e:
                logger.error("Error in promotion trial: %s", e, exc_info=True)
                
        asyncio.create_task(background_task())

    async def faction_leave(self, interaction: discord.Interaction, session_id: int, user_id: int):
        await interaction.response.edit_message(content="You close the faction menu.", view=None, embed=None)
