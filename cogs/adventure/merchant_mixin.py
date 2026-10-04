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

        embeds = [_merchant_embed(session_id, extra_note=detour_note)]
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
                view = SyncChoiceView(self, session_id, session["turn_order"], session["choices"], party, merchant)
            else:
                turn_uid = db.current_turn_user_id(session)
                actor_char = await adb(db.get_character, turn_uid)
                embeds = scene_embed(session, actor_char, session["scene_title"], session["narrative"],
                                     session["choices"])
                view = ChoiceView(self, session_id, turn_uid, session["choices"], actor_char, merchant)

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
        embeds = [_merchant_embed(session_id, extra_note=f"The party couldn't agree to {action_label} this time.")]
        view = MerchantView(self, session_id, session["turn_order"])
        if not interaction.response.is_done():
            await interaction.response.edit_message(embeds=embeds, view=view)
        else:
            await interaction.edit_original_response(embeds=embeds, view=view)

    async def open_buy_menu(self, interaction: discord.Interaction, session_id: int):
        """Task 2's Buy -- ephemeral, no LLM call needed (stock was already
        generated at shop entry), so this responds instantly."""
        session = await adb(db.get_session, session_id)
        merchant = session["merchant"]
        stock = [item for item in merchant.get("stock", []) if item.get("quantity", 0) > 0]
        if not stock:
            current_day, _, _ = await adb(db.get_session_time, session_id)
            await interaction.response.send_message(
                f"📦 The merchant's stock is sold out for today. Wares will restock on **Day {current_day + 1}**!",
                ephemeral=True
            )
            return
        discount = merchant.get("discount_pct", 0)
        view = BuySelectView(self, session_id, stock, discount)
        lines = []
        for i in stock:
            price = _discounted_price(i["price"], discount)
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
        session = db.get_session(session_id)
        merchant = session["merchant"]
        stock = merchant.get("stock", [])
        entry = next((i for i in stock if i["name"] == item_name and i.get("quantity", 0) > 0), None)
        if not entry and " #" in item_name:
            base_name = item_name.rsplit(" #", 1)[0]
            entry = next((i for i in stock if i["name"] == base_name and i.get("quantity", 0) > 0), None)
        if not entry:
            await interaction.response.send_message("That item is no longer available.", ephemeral=True)
            return

        price = _discounted_price(entry["price"], merchant.get("discount_pct", 0))
        char = db.get_character(user_id)
        if not char or char["gold"] < price:
            await interaction.response.send_message(f"You don't have enough gold ({price}g needed).",
                                                      ephemeral=True)
            return

        if not db.can_add_item(user_id, slot_cost=1):
            cap = inventory_capacity(char.get("str_", 1))
            used = db.used_slots(user_id)
            await interaction.response.send_message(
                f"🎒 Your inventory is full ({used}/{cap} slots). Sell or drop items before buying!",
                ephemeral=True
            )
            return

        db.apply_hp_mp_delta(user_id, 0, 0, -price)
        effect_val = entry.get("effect") or entry.get("description", "")
        db.add_item(user_id, entry["name"], entry["item_type"], effect_val, entry.get("slot_cost", 1))
        entry["quantity"] -= 1

        active_key = merchant.get("active_store_key")
        if active_key and "catalogues" in merchant and active_key in merchant["catalogues"]:
            merchant["catalogues"][active_key]["stock"] = stock

        db.save_merchant_state(session_id, merchant)
        await interaction.response.edit_message(
            content=f"🛒 You bought **{entry['name']}** for **{price}g**!", view=None)

    async def open_sell_menu(self, interaction: discord.Interaction, session_id: int):
        """Task 2's Sell -- needs an LLM call to price the player's live
        inventory, so this defers first (ephemeral) then follows up."""
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id
        inventory = db.get_inventory(user_id)
        from mechanics.combat.items import is_key_item
        carried = [i for i in inventory if not i.get("equipped") and not is_key_item(i)]
        if not carried:
            await interaction.followup.send("You have no unequipped items to sell (equipped gear and key items cannot be sold).", ephemeral=True)
            return
        prices = await game_engine.evaluate_items_for_sale(carried)
        session = db.get_session(session_id)
        discount = session["merchant"].get("discount_pct", 0)
        priced_items = [
            {"id": item["id"], "name": item["name"],
             "price": _sell_bonus_price(prices.get(item["name"], 3), discount)}
            for item in carried
        ]
        view = SellSelectView(self, session_id, priced_items)
        lines = "\n".join(f"**{i['name']}** — {i['price']}g" for i in priced_items)
        await interaction.followup.send(content=f"**The merchant offers:**\n{lines}", view=view, ephemeral=True)

    async def sell_item(self, interaction: discord.Interaction, session_id: int, user_id: int,
                         item_id: int, item_name: str, price: int):
        """Independent & non-blocking (Task 3.2): only THIS player's gold
        and inventory change."""
        inv = db.get_inventory(user_id)
        match = next((i for i in inv if i["id"] == item_id), None)
        if not match:
            await interaction.response.send_message("You no longer have that item.", ephemeral=True)
            return
        if match.get("equipped"):
            await interaction.response.send_message("❌ You cannot sell an item while it is equipped. Unequip it first!", ephemeral=True)
            return
        from mechanics.combat.items import is_key_item
        if is_key_item(match):
            await interaction.response.send_message("❌ Key narrative items cannot be sold.", ephemeral=True)
            return
        db.remove_item(user_id, match["id"])
        db.apply_hp_mp_delta(user_id, 0, 0, price)
        await interaction.response.edit_message(
            content=f"💰 You sold **{item_name}** for **{price}g**!", view=None)

    async def resolve_haggle(self, interaction: discord.Interaction, session_id: int, user_id: int):
        """Task 2's Haggle: up to 3 attempts per encounter (shared across
        the whole party, not per-player), difficulty scaling with each
        attempt. Success applies a cumulative discount to Buy (lower
        price) and Sell (higher payout) for the rest of the encounter."""
        session = db.get_session(session_id)
        merchant = session["merchant"]
        attempts = merchant.get("haggle_attempts", 0)
        char = db.get_character(user_id)

        if attempts >= 3:
            note = "The merchant has grown tired of haggling — no more attempts this visit."
        else:
            requirement = 4 + attempts * 2  # scales up each attempt: 4, 6, 8
            check_mode = db.get_settings(user_id).get("debug_check_mode", "off")
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
            db.save_merchant_state(session_id, merchant)

        embeds = [_merchant_embed(session_id, extra_note=note)]
        view = MerchantView(self, session_id, session["turn_order"])
        if not interaction.response.is_done():
            await interaction.response.edit_message(embeds=embeds, view=view)
        else:
            await interaction.edit_original_response(embeds=embeds, view=view)

    async def _show_rumor_menu(self, interaction: discord.Interaction, session_id: int):
        session = db.get_session(session_id)
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
        session = db.get_session(session_id)
        merchant = session["merchant"]
        rumors = merchant.get("rumors", [])
        if idx >= len(rumors) or rumors[idx].get("revealed"):
            await self._show_rumor_menu(interaction, session_id)  # stale click -- just re-render
            return

        char = db.get_character(user_id)
        check_mode = db.get_settings(user_id).get("debug_check_mode", "off")
        check = resolve_check(char["cha"], 5, char["luk"], check_mode=check_mode)
        rumors[idx]["revealed"] = True
        db.save_merchant_state(session_id, merchant)

        if check.succeeded:
            rumor_text = rumors[idx]["text"]
            result_text = f"*\"{rumor_text}\"*\n\n*(📜 Logged as a Clue & Bounty Hook in your Quest System!)*"
            new_history = game_engine.push_history(session["history"],
                                                    f"[Rumor] {char['name']} learned: {rumor_text}")
            db.save_session_scene(session_id, session["scene_title"], session["narrative"],
                                   session["choices"], new_history)

            # Tie directly into Quest System & Caseboard: add as clue to active quest or spawn a side bounty!
            cur_ch = db.get_session_chapter(session_id) or 1
            db.add_session_clue(
                session_id=session_id,
                title=rumor_text[:60],
                lead_text=rumor_text,
                category="testimonial",
                source_location=session.get("current_location", "Merchant Shop"),
                linked_npc=merchant.get("name", "Merchant"),
                chapter=cur_ch
            )
            active_quests = db.get_session_quests(session_id, status="Active")
            if active_quests:
                aq = active_quests[0]
                existing_clues = aq.get("current_clues") or ""
                new_clue_bullet = f"• {rumor_text[:120]}"
                clues_combined = f"{existing_clues}\n{new_clue_bullet}".strip()
                db.upsert_quest(
                    session_id=session_id,
                    quest_id=aq["quest_id"],
                    quest_type=aq.get("quest_type", "Main Quest"),
                    title=aq["title"],
                    objective=aq["objective"],
                    progress=aq.get("progress", ""),
                    current_clues=clues_combined,
                    status="Active",
                    reward_xp=aq.get("reward_xp", 50),
                    reward_gold=aq.get("reward_gold", 25),
                    reward_stat_points=aq.get("reward_stat_points", 0),
                    quest_notes=aq.get("quest_notes")
                )
            else:
                import uuid
                b_id = f"BNT-{uuid.uuid4().hex[:8].upper()}"
                db.upsert_quest(
                    session_id=session_id,
                    quest_id=b_id,
                    quest_type="Investigation",
                    title=f"Rumor: {rumor_text[:40]}...",
                    objective=rumor_text[:200],
                    progress="0/1 Investigated",
                    current_clues=f"• Learned from {merchant.get('flavor_name', 'merchant')}",
                    status="Available",
                    reward_xp=60,
                    reward_gold=30,
                    reward_stat_points=0
                )
        else:
            result_text = (f"**{char['name']}** can't get a clear answer — the merchant's story doesn't "
                            f"quite add up. ({check.chance}% chance — {check.tier_label})")

        embeds = [discord.Embed(title="👂 Ask Around", description=result_text, color=discord.Color.dark_gold())]
        view = RumorView(self, session_id, rumors)
        if not interaction.response.is_done():
            await interaction.response.edit_message(embeds=embeds, view=view)
        else:
            await interaction.edit_original_response(embeds=embeds, view=view)

    async def return_to_merchant_view(self, interaction: discord.Interaction, session_id: int):
        session = db.get_session(session_id)
        embeds = [_merchant_embed(session_id)]
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
        session = db.get_session(session_id)
        merchant = session["merchant"]
        merchant["active"] = False
        merchant["available"] = False  # this encounter is resolved; a future scene rolls fresh
        db.save_merchant_state(session_id, merchant)

        party = [(db.get_character(uid), db.get_inventory(uid)) for uid in session["turn_order"]]
        if session["mode"] == "sync":
            waiting_on = [uid for uid in session["turn_order"] if str(uid) not in session["pending_picks"]]
            embeds = sync_scene_embed(session, party, session["scene_title"], session["narrative"],
                                      session["choices"], waiting_on)
            view = SyncChoiceView(self, session_id, session["turn_order"], session["choices"], party, merchant)
        else:
            turn_uid = db.current_turn_user_id(session)
            actor_char = db.get_character(turn_uid)
            embeds = scene_embed(session, actor_char, session["scene_title"], session["narrative"],
                                 session["choices"])
            view = ChoiceView(self, session_id, turn_uid, session["choices"], actor_char, merchant)

        content = "You step away from the merchant's stall."
        if not interaction.response.is_done():
            await interaction.response.edit_message(content=content, embeds=embeds, view=view)
        else:
            await interaction.edit_original_response(content=content, embeds=embeds, view=view)
