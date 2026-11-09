import asyncio
import discord
import db
from db import adb
import game_engine
from character_data import inventory_capacity
from skill_check import resolve_check
from mechanics.combat.merchant import (
    build_merchant_embed as _merchant_embed,
    discounted_price as _discounted_price,
    sell_bonus_price as _sell_bonus_price,
    compute_item_resale_payout,
    MerchantView,
    BuySelectView,
    SellSelectView,
    RumorView,
)
from .embeds import scene_embed, sync_scene_embed
from .views import ChoiceView, SyncChoiceView


class MerchantMixin:
    """Merchant shop entry, detour voting, buy/sell menus, haggling, and rumor handlers for AdventureCog."""

    async def enter_merchant_shop(self, interaction: discord.Interaction, session_id: int,
                                   initiator_id: int, detour_note: str = None, is_phone_shop: bool = False,
                                   merchant_type: str = "general_merchant"):
        """Generates the shop (one combined LLM call: intro + stock +
        rumors), persists it, and swaps in MerchantView. Called either
        directly (solo) or as a vote's on_unanimous/detour-success
        callback -- in both cases `interaction` hasn't been responded to
        yet, so we defer (the LLM call can take a few seconds) and finish
        with edit_original_response."""
        if not interaction.response.is_done():
            await interaction.response.defer()
        session = await adb(db.get_session, session_id)
        merchant = session["merchant"]
        party = list(await asyncio.gather(
            *[(asyncio.gather(adb(db.get_character, uid), adb(db.get_inventory, uid)))
              for uid in session["turn_order"]]
        ))

        current_day, current_minute, _ = await adb(db.get_session_time, session_id)
        loc = session.get("current_location", "")

        from mechanics.combat.merchant import (
            get_store_key,
            get_or_create_merchant_catalogue,
            update_merchant_catalogue,
        )

        store_key = get_store_key(merchant, is_phone_shop=is_phone_shop, merchant_type=merchant_type, location=loc)
        cat_entry, needs_restock = get_or_create_merchant_catalogue(merchant, store_key, current_day, current_minute)

        if needs_restock:
            shop = await game_engine.generate_merchant_shop(
                party, merchant.get("flavor_name", ""), merchant.get("flavor_description", ""), session,
                is_phone_shop=is_phone_shop, merchant_type=merchant_type)
            cat_entry = update_merchant_catalogue(merchant, store_key, shop, current_day, current_minute)

        merchant.update({
            "active": True,
            "active_store_key": store_key,
            "merchant_type": merchant_type,
            "is_phone_shop": is_phone_shop,
            "intro_narrative": cat_entry["intro_narrative"],
            "stock": cat_entry["stock"],
            "rumors": cat_entry["rumors"],
            "haggle_attempts": cat_entry.get("haggle_attempts", 0),
            "discount_pct": cat_entry.get("discount_pct", 0),
            "restock_day": cat_entry.get("restock_day", current_day),
            "restock_minute": cat_entry.get("restock_minute", current_minute),
        })
        await adb(db.save_merchant_state, session_id, merchant)

        embeds = [await adb(_merchant_embed, session_id, detour_note)]
        view = MerchantView(self, session_id, session["turn_order"], is_phone_shop=is_phone_shop)
        await interaction.edit_original_response(content=None, embeds=embeds, view=view)

    async def attempt_merchant_detour(self, interaction: discord.Interaction, session_id: int, initiator_id: int):
        """Task 3.1's fallback when the party-entry vote isn't unanimous:
        one party-wide CHA check (using the initiating player's character)
        to see if the group still gets talked into stopping anyway."""
        initiator, _settings = await asyncio.gather(
            adb(db.get_character, initiator_id),
            adb(db.get_settings, initiator_id),
        )
        check_mode = _settings.get("debug_check_mode", "off")
        check = resolve_check(initiator["cha"], 6, initiator["luk"], check_mode=check_mode)
        if check.succeeded:
            await self.enter_merchant_shop(
                interaction, session_id, initiator_id,
                detour_note=(f"Not everyone agreed, but **{initiator['name']}** convinces the group to "
                              f"stop anyway. ({check.chance}% chance — {check.tier_label})"))
        else:
            session = await adb(db.get_session, session_id)
            merchant = session["merchant"]
            merchant["active"] = False
            merchant["available"] = False
            await adb(db.save_merchant_state, session_id, merchant)

            party = list(await asyncio.gather(
                *[(asyncio.gather(adb(db.get_character, uid), adb(db.get_inventory, uid)))
                  for uid in session["turn_order"]]
            ))
            if session["mode"] == "sync":
                waiting_on = [uid for uid in session["turn_order"] if str(uid) not in session["pending_picks"]]
                embeds = sync_scene_embed(session, party, session["scene_title"], session["narrative"],
                                          session["choices"], waiting_on)
                view = await SyncChoiceView.create(
                    self, session_id, session["turn_order"], session["choices"], party, merchant, session=session,
                )
            else:
                turn_uid = db.current_turn_user_id(session)
                party_by_uid = {
                    (c.get("user_id") or c.get("id")): (c, inv)
                    for c, inv in party
                    if c
                }
                if turn_uid in party_by_uid:
                    actor_char, actor_inv = party_by_uid[turn_uid]
                else:
                    actor_char = await adb(db.get_character, turn_uid)
                    actor_inv = None
                embeds = scene_embed(session, actor_char, session["scene_title"], session["narrative"],
                                     session["choices"])
                view = await ChoiceView.create(
                    self, session_id, turn_uid, session["choices"], actor_char, merchant,
                    session=session, actor_inv=actor_inv,
                )

            content = (f"The party can't agree on stopping, and **{initiator['name']}**'s attempt to "
                       f"convince them otherwise falls flat. ({check.chance}% chance — {check.tier_label}) "
                       f"You continue on your way.")
            if not interaction.response.is_done():
                await interaction.response.edit_message(content=content, embeds=embeds, view=view)
            else:
                await interaction.edit_original_response(content=content, embeds=embeds, view=view)

    async def _merchant_consensus_failed(self, interaction: discord.Interaction, session_id: int, action_label: str):
        """Haggle/Ask/Leave voted down (Task 3.2 has no skill-check
        fallback for these, unlike shop entry) -- redisplay the shop
        unchanged with a short note."""
        session = await adb(db.get_session, session_id)
        embeds = [await adb(_merchant_embed, session_id, f"The party couldn't agree to {action_label} this time.")]
        view = MerchantView(self, session_id, session["turn_order"])
        if not interaction.response.is_done():
            await interaction.response.edit_message(embeds=embeds, view=view)
        else:
            await interaction.edit_original_response(embeds=embeds, view=view)

    async def open_buy_menu(self, interaction: discord.Interaction, session_id: int):
        """Task 2's Buy -- ephemeral, no LLM call needed (stock was already
        generated at shop entry), so this responds instantly."""
        from mechanics.combat.merchant import (
            compute_effective_shop_item_price,
            get_anomalous_shop_faction_context,
        )

        session = await adb(db.get_session, session_id)
        merchant = session["merchant"]
        is_phone_shop = bool(merchant.get("is_phone_shop", False))
        shop_ctx = await adb(
            get_anomalous_shop_faction_context,
            session,
            session.get("current_location", ""),
            is_phone_shop,
            interaction.user.id,
        )
        if not shop_ctx.get("allowed", True):
            await interaction.response.send_message(
                shop_ctx.get("access_denied_reason") or "Access denied to this faction store.",
                ephemeral=True,
            )
            return
        if shop_ctx.get("shrine_daily_exhausted"):
            await interaction.response.send_message(
                "Daily Sacred Shrine provisions (3/3) have been claimed today. Stock refreshes tomorrow morning.",
                ephemeral=True,
            )
            return

        stock = [item for item in merchant.get("stock", []) if item.get("quantity", 0) > 0]
        if not stock:
            current_day, _, _ = await adb(db.get_session_time, session_id)
            await interaction.response.send_message(
                f"📦 The merchant's stock is sold out for today. Wares will restock on **Day {current_day + 1}**!",
                ephemeral=True
            )
            return
        discount = merchant.get("discount_pct", 0)
        view = BuySelectView(self, session_id, stock, discount, shop_ctx=shop_ctx, user_id=interaction.user.id)
        lines = []
        for i in stock:
            price = compute_effective_shop_item_price(i, shop_ctx=shop_ctx, discount_pct=discount)
            t_str = i.get("item_type", "Item")
            desc = (i.get("description") or "").strip()
            if len(desc) > 120:
                desc = desc[:117] + "..."
            line = f"• **{i['name']}** ({t_str}) — {price}g (x{i.get('quantity', 1)})\n  └ *{desc}*" if desc else f"• **{i['name']}** ({t_str}) — {price}g (x{i.get('quantity', 1)})"
            lines.append(line)

        content = "**For sale:**\n" + "\n".join(lines)
        if len(content) > 1950:
            content = content[:1920] + "\n\n*(additional items available in dropdown below)*"
        await interaction.response.send_message(content=content, view=view, ephemeral=True)

    async def buy_item(self, interaction: discord.Interaction, session_id: int, user_id: int, item_name: str):
        """Independent & non-blocking (Task 3.2): only THIS player's gold
        and inventory change. Stock quantity is shared/server-authoritative
        (first come, first served), which is a separate concern from
        personal gold/inventory and not something Task 3.2 asks to be
        per-player."""
        import json as _json
        from mechanics.combat.merchant import (
            compute_effective_shop_item_price,
            get_anomalous_shop_faction_context,
            mark_vault_requisition_claimed,
            stamp_discounted_purchase_metadata,
        )
        from mechanics.system.concurrency import LockAcquisitionError, distributed_session_lock

        try:
            async with distributed_session_lock(session_id, raise_http_error=False):
                session = await adb(db.get_session, session_id)
                if not session:
                    await interaction.response.send_message("Session not found.", ephemeral=True)
                    return
                sess_members = set(int(u) for u in ((await adb(db.get_session_members, session_id)) or []) if u is not None)
                sess_members.update(int(u) for u in (session.get("turn_order") or []) if u is not None)
                if session.get("host_user_id") is not None:
                    sess_members.add(int(session["host_user_id"]))
                if int(user_id) not in sess_members:
                    await interaction.response.send_message("You're not in this session.", ephemeral=True)
                    return
                merchant = session["merchant"]
                is_phone_shop = bool(merchant.get("is_phone_shop", False))
                shop_ctx = await adb(
                    get_anomalous_shop_faction_context,
                    session,
                    session.get("current_location", ""),
                    is_phone_shop,
                    user_id,
                )
                if not shop_ctx.get("allowed", True):
                    await interaction.response.send_message(
                        shop_ctx.get("access_denied_reason") or "Access denied to this faction store.",
                        ephemeral=True,
                    )
                    return
                if shop_ctx.get("shrine_daily_exhausted"):
                    await interaction.response.send_message(
                        "Daily Sacred Shrine provisions (3/3) have been claimed today. Stock refreshes tomorrow morning.",
                        ephemeral=True,
                    )
                    return

                stock = merchant.get("stock", [])
                entry = next((i for i in stock if i["name"] == item_name and i.get("quantity", 0) > 0), None)
                if not entry and " #" in item_name:
                    base_name = item_name.rsplit(" #", 1)[0]
                    entry = next((i for i in stock if i["name"] == base_name and i.get("quantity", 0) > 0), None)
                if not entry:
                    await interaction.response.send_message("That item is no longer available.", ephemeral=True)
                    return

                discount_pct = merchant.get("discount_pct", 0)
                price = compute_effective_shop_item_price(entry, shop_ctx=shop_ctx, discount_pct=discount_pct)

                char = await adb(db.get_character, user_id)
                if not char or (char.get("gold", 0) or 0) < price:
                    await interaction.response.send_message(
                        f"You don't have enough gold ({price}g needed).",
                        ephemeral=True,
                    )
                    return

                effect_val = str(entry.get("effect") or entry.get("description", ""))
                if shop_ctx.get("is_monastic_free_shop") or shop_ctx.get("is_public_discounted_shop"):
                    for prefix in ("[ITEM_JSON]", "[GEAR_JSON]", "[CONSUMABLE_JSON]"):
                        if effect_val.startswith(prefix):
                            try:
                                meta_obj = _json.loads(effect_val[len(prefix):])
                                if shop_ctx.get("is_monastic_free_shop"):
                                    meta_obj["shrine_sacred_grant"] = True
                                if shop_ctx.get("is_public_discounted_shop"):
                                    meta_obj["purchase_price_paid"] = price
                                    meta_obj["public_requisition_item"] = True
                                effect_val = f"{prefix}{_json.dumps(meta_obj)}"
                            except Exception:
                                pass
                            break
                    else:
                        if shop_ctx.get("is_monastic_free_shop"):
                            effect_val = f"[CONSUMABLE_JSON]{_json.dumps({'description': effect_val, 'shrine_sacred_grant': True})}"
                        elif shop_ctx.get("is_public_discounted_shop"):
                            effect_val = f"[CONSUMABLE_JSON]{_json.dumps({'description': effect_val, 'purchase_price_paid': price, 'public_requisition_item': True})}"
                elif shop_ctx.get("is_event_discounted_shop"):
                    effect_val = stamp_discounted_purchase_metadata(effect_val, price)

                slot_cost_val = int(entry.get("slot_cost", 1) or 1)
                can_fit = await adb(
                    db.can_add_item,
                    user_id,
                    slot_cost_val,
                    entry["name"],
                    entry.get("item_type", "Item"),
                    effect_val,
                )
                if not can_fit:
                    cap = await adb(db.get_character_inventory_capacity, user_id, char)
                    used = await adb(db.used_slots, user_id)
                    await interaction.response.send_message(
                        f"🎒 Your inventory is full ({used}/{cap} slots). Sell or drop items before buying!",
                        ephemeral=True,
                    )
                    return

                try:
                    await adb(
                        db.atomic_merchant_purchase,
                        user_id,
                        entry["name"],
                        entry.get("item_type", "Item"),
                        effect_val,
                        slot_cost_val,
                        price,
                    )
                except (ValueError, LookupError) as exc:
                    await interaction.response.send_message(str(exc), ephemeral=True)
                    return

                if shop_ctx.get("is_monastic_free_shop"):
                    from mechanics.social.factions import get_anomalous_faction_state, save_anomalous_faction_state
                    a_state = await adb(get_anomalous_faction_state, session_id, user_id)
                    new_claims = int(a_state.get("shrine_free_claims_today", a_state.get("shrine_free_claimed_today", 0)) or 0) + 1
                    a_state["shrine_free_claims_today"] = new_claims
                    a_state["shrine_free_claimed_today"] = new_claims
                    await adb(save_anomalous_faction_state, session_id, a_state, user_id)

                entry["quantity"] -= 1

                active_key = merchant.get("active_store_key")
                if active_key and "catalogues" in merchant and active_key in merchant["catalogues"]:
                    merchant["catalogues"][active_key]["stock"] = stock

                if entry.get("is_vault_requisition"):
                    claimed_reqs = mark_vault_requisition_claimed(session, entry.get("name", ""))
                    if claimed_reqs is not None:
                        await adb(db.update_session, session_id, extra={"anomalous_vault_requisitions": claimed_reqs})

                await adb(db.save_merchant_state, session_id, merchant)
                await adb(game_engine.evaluate_quest_state_predicates, session_id, user_id)
        except LockAcquisitionError:
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "⏳ Another shop or turn action is resolving for this session. Please retry in a moment.",
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(
                    "⏳ Another shop or turn action is resolving for this session. Please retry in a moment.",
                    ephemeral=True,
                )
            return

        await interaction.response.edit_message(
            content=f"🛒 You bought **{entry['name']}** for **{price}g**!", view=None)

    async def open_sell_menu(self, interaction: discord.Interaction, session_id: int):
        """Evaluates sellable inventory items using unified deterministic resale pricing."""
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id
        inventory, session, char = await asyncio.gather(
            adb(db.get_inventory, user_id),
            adb(db.get_session, session_id),
            adb(db.get_character, user_id),
        )
        priced_items = []
        for item in (inventory or []):
            payout, reject_reason = compute_item_resale_payout(dict(item), session, char)
            if reject_reason:
                continue
            priced_items.append({"id": item["id"], "name": item["name"], "price": payout})
        if not priced_items:
            await interaction.followup.send(
                "You have no unequipped items to sell (equipped gear, key items, and digital items cannot be sold).",
                ephemeral=True,
            )
            return
        view = SellSelectView(self, session_id, priced_items, user_id=user_id)
        lines = "\n".join(f"**{i['name']}** — {i['price']}g" for i in priced_items)
        await interaction.followup.send(content=f"**The merchant offers:**\n{lines}", view=view, ephemeral=True)

    async def sell_item(self, interaction: discord.Interaction, session_id: int, user_id: int,
                         item_id: int, item_name: str, price: int):
        """Independent & non-blocking: verifies resale eligibility and price server-side inside UnitOfWork."""
        inv, session, char = await asyncio.gather(
            adb(db.get_inventory, user_id),
            adb(db.get_session, session_id),
            adb(db.get_character, user_id),
        )
        match = next((dict(i) for i in (inv or []) if i.get("id") == item_id), None)
        if not match:
            await interaction.response.send_message("You no longer have that item.", ephemeral=True)
            return
        verified_price, reject_reason = compute_item_resale_payout(match, session, char)
        if reject_reason:
            await interaction.response.send_message(f"❌ {reject_reason}.", ephemeral=True)
            return
        sold = await adb(db.sell_inventory_item, user_id, match["id"], verified_price)
        if not sold:
            await interaction.response.send_message("You no longer have that item.", ephemeral=True)
            return
        await interaction.response.edit_message(
            content=f"💰 You sold **{match.get('name', item_name)}** for **{verified_price}g**!", view=None)

    async def resolve_haggle(self, interaction: discord.Interaction, session_id: int, user_id: int):
        """Task 2's Haggle: up to 3 attempts per encounter (shared across
        the whole party, not per-player), difficulty scaling with each
        attempt. Success applies a cumulative discount to Buy (lower
        price) and Sell (higher payout) for the rest of the encounter."""
        from mechanics.system.concurrency import LockAcquisitionError, distributed_session_lock

        try:
            async with distributed_session_lock(session_id, raise_http_error=False):
                session = await adb(db.get_session, session_id)
                merchant = session["merchant"]
                attempts = merchant.get("haggle_attempts", 0)
                char = await adb(db.get_character, user_id)

                if attempts >= 3:
                    note = "The merchant has grown tired of haggling — no more attempts this visit."
                else:
                    requirement = 4 + attempts * 2  # scales up each attempt: 4, 6, 8
                    check_mode = (await adb(db.get_settings, user_id)).get("debug_check_mode", "off")
                    check = resolve_check(char["cha"], requirement, char["luk"], check_mode=check_mode)
                    merchant["haggle_attempts"] = attempts + 1
                    if check.succeeded:
                        merchant["discount_pct"] = min(30, merchant.get("discount_pct", 0) + 10)
                        note = (f"**{char['name']}** haggles skillfully! ({check.chance}% chance — {check.tier_label}) "
                                f"The party now gets a **{merchant['discount_pct']}%** discount buying, and better "
                                f"prices selling.")
                    else:
                        note = (f"**{char['name']}**'s haggling falls flat. ({check.chance}% chance — "
                                f"{check.tier_label}) Prices are unchanged.")
                    active_key = merchant.get("active_store_key")
                    if active_key and "catalogues" in merchant and active_key in merchant["catalogues"]:
                        merchant["catalogues"][active_key]["haggle_attempts"] = merchant["haggle_attempts"]
                        merchant["catalogues"][active_key]["discount_pct"] = merchant["discount_pct"]
                    await adb(db.save_merchant_state, session_id, merchant)
        except LockAcquisitionError:
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "⏳ Another haggle or turn action is currently resolving. Please retry in a moment.",
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(
                    "⏳ Another haggle or turn action is currently resolving. Please retry in a moment.",
                    ephemeral=True,
                )
            return

        embeds = [await adb(_merchant_embed, session_id, note)]
        view = MerchantView(self, session_id, session["turn_order"])
        if not interaction.response.is_done():
            await interaction.response.edit_message(embeds=embeds, view=view)
        else:
            await interaction.edit_original_response(embeds=embeds, view=view)

    async def _show_rumor_menu(self, interaction: discord.Interaction, session_id: int):
        session = await adb(db.get_session, session_id)
        rumors = session["merchant"].get("rumors", [])
        embeds = [discord.Embed(title="👂 Ask Around", description="Pick a topic to ask the merchant about:",
                               color=discord.Color.dark_gold())]
        view = RumorView(self, session_id, rumors)
        if not interaction.response.is_done():
            await interaction.response.edit_message(embeds=embeds, view=view)
        else:
            await interaction.edit_original_response(embeds=embeds, view=view)

    async def reveal_rumor(self, interaction: discord.Interaction, session_id: int, user_id: int, idx: int):
        """Runs a skill check for how useful/accurate the rumor is, then
        marks it revealed EITHER WAY so it can't be re-attempted/farmed
        (Task 2's Ask spec). On success, logs the rumor text into the
        session history so future narration can stay consistent with it."""
        from mechanics.system.concurrency import LockAcquisitionError, distributed_session_lock

        try:
            async with distributed_session_lock(session_id, raise_http_error=False):
                session = await adb(db.get_session, session_id)
                merchant = session["merchant"]
                rumors = merchant.get("rumors", [])
                if idx >= len(rumors) or rumors[idx].get("revealed"):
                    stale_click = True
                else:
                    stale_click = False
                    char, _settings = await asyncio.gather(
                        adb(db.get_character, user_id),
                        adb(db.get_settings, user_id),
                    )
                    check_mode = _settings.get("debug_check_mode", "off")
                    check = resolve_check(char["cha"], 5, char["luk"], check_mode=check_mode)
                    rumors[idx]["revealed"] = True
                    await adb(db.save_merchant_state, session_id, merchant)

                    if check.succeeded:
                        rumor_entry = rumors[idx] if isinstance(rumors[idx], dict) else {"text": str(rumors[idx])}
                        rumor_text = rumor_entry.get("text", "")
                        new_history = game_engine.push_history(session["history"],
                                                                f"[Rumor] {char['name']} learned: {rumor_text}")
                        await adb(
                            db.save_session_scene,
                            session_id,
                            session["scene_title"],
                            session["narrative"],
                            session["choices"],
                            new_history,
                        )

                        linked_qid = str(rumor_entry.get("linked_quest_id") or "").strip()
                        linked_nid = str(rumor_entry.get("linked_node_id") or "").strip()
                        if linked_nid:
                            from mechanics.combat.merchant import reveal_hidden_node_from_rumor
                            await adb(reveal_hidden_node_from_rumor, session_id, linked_nid)
                        if linked_qid or linked_nid:
                            cur_ch = (await adb(db.get_session_chapter, session_id)) or 1
                            await adb(
                                db.add_session_clue,
                                session_id=session_id,
                                title=rumor_text[:60],
                                lead_text=rumor_text,
                                category="testimonial",
                                source_location=session.get("current_location", "Merchant Shop"),
                                linked_npc=str(rumor_entry.get("linked_npc") or merchant.get("name", "Merchant")),
                                quest_id=linked_qid,
                                chapter=cur_ch,
                            )
                            result_text = f"*\"{rumor_text}\"*\n\n*(📜 Logged to your Clue Caseboard!)*"
                        else:
                            result_text = f"*\"{rumor_text}\"*"
                    else:
                        result_text = (f"**{char['name']}** can't get a clear answer — the merchant's story doesn't "
                                        f"quite add up. ({check.chance}% chance — {check.tier_label})")
        except LockAcquisitionError:
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "⏳ Another investigation or turn action is currently resolving. Please retry in a moment.",
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(
                    "⏳ Another investigation or turn action is currently resolving. Please retry in a moment.",
                    ephemeral=True,
                )
            return

        if stale_click:
            await self._show_rumor_menu(interaction, session_id)
            return

        embeds = [discord.Embed(title="👂 Ask Around", description=result_text, color=discord.Color.dark_gold())]
        view = RumorView(self, session_id, rumors)
        if not interaction.response.is_done():
            await interaction.response.edit_message(embeds=embeds, view=view)
        else:
            await interaction.edit_original_response(embeds=embeds, view=view)

    async def return_to_merchant_view(self, interaction: discord.Interaction, session_id: int):
        session = await adb(db.get_session, session_id)
        embeds = [await adb(_merchant_embed, session_id)]
        view = MerchantView(self, session_id, session["turn_order"])
        if not interaction.response.is_done():
            await interaction.response.edit_message(embeds=embeds, view=view)
        else:
            await interaction.edit_original_response(embeds=embeds, view=view)

    async def leave_merchant(self, interaction: discord.Interaction, session_id: int):
        """Task 2's Leave: clears the shop state and resumes the main story
        loop exactly where it left off -- Talk-to-Merchant/Leave are
        turn-neutral side trips (no LLM call, no turn advancement), so we
        just re-render the SAME scene/choices from session state rather
        than generating anything new."""
        session = await adb(db.get_session, session_id)
        merchant = session["merchant"]
        merchant["active"] = False
        merchant["available"] = False  # this encounter is resolved; a future scene rolls fresh
        await adb(db.save_merchant_state, session_id, merchant)

        turn_uids = list(session["turn_order"])
        chars = await asyncio.gather(*(adb(db.get_character, uid) for uid in turn_uids))
        invs = await asyncio.gather(*(adb(db.get_inventory, uid) for uid in turn_uids))
        party = list(zip(chars, invs))
        if session["mode"] == "sync":
            waiting_on = [uid for uid in session["turn_order"] if str(uid) not in session["pending_picks"]]
            embeds = sync_scene_embed(session, party, session["scene_title"], session["narrative"],
                                      session["choices"], waiting_on)
            view = await SyncChoiceView.create(
                self, session_id, session["turn_order"], session["choices"], party, merchant, session=session,
            )
        else:
            turn_uid = db.current_turn_user_id(session)
            party_by_uid = {
                (c.get("user_id") or c.get("id")): (c, inv)
                for c, inv in party
                if c
            }
            if turn_uid in party_by_uid:
                actor_char, actor_inv = party_by_uid[turn_uid]
            else:
                actor_char = await adb(db.get_character, turn_uid)
                actor_inv = None
            embeds = scene_embed(session, actor_char, session["scene_title"], session["narrative"],
                                 session["choices"])
            view = await ChoiceView.create(
                self, session_id, turn_uid, session["choices"], actor_char, merchant,
                session=session, actor_inv=actor_inv,
            )

        content = "You step away from the merchant's stall."
        if not interaction.response.is_done():
            await interaction.response.edit_message(content=content, embeds=embeds, view=view)
        else:
            await interaction.edit_original_response(content=content, embeds=embeds, view=view)
