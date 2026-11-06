from __future__ import annotations
"""
Discord UI Views and Embed Builders for Merchant Encounters.
Extracted from mechanics/combat/merchant.py to respect Layer 4 separation of concerns.
"""
from typing import TYPE_CHECKING, List, Dict, Any, Optional
import discord

import db
from mechanics.combat.merchant import (
    MERCHANT_ARCHETYPES,
    compute_effective_shop_item_price,
    discounted_price,
)

if TYPE_CHECKING:
    from cogs.adventure.cog import AdventureCog


def build_merchant_embed(session_id: int, extra_note: str | None = None) -> discord.Embed:
    session = db.get_session(session_id)
    merchant = session["merchant"]
    is_phone = merchant.get("is_phone_shop", False)
    scen_key = session.get("scenario", "fantasy") if session else "fantasy"
    merchant_type = merchant.get("merchant_type", "general_merchant")
    arch = MERCHANT_ARCHETYPES.get(merchant_type, MERCHANT_ARCHETYPES.get("general_merchant", {}))
    arch_emoji = arch.get("emoji", "🛍️")
    arch_title = arch.get("title", "The Merchant")

    current_day, current_minute, _ = db.get_session_time(session_id)
    next_day = current_day + 1

    if is_phone:
        from mechanics.system.phone import get_phone_branding
        branding = get_phone_branding(scen_key)
        embed = discord.Embed(
            title=f"📦 {branding['shop_app_name']}",
            description=merchant.get("intro_narrative", f"Welcome to {branding['shop_app_name']}! Browse items delivered straight to your inventory."),
            color=branding["color"]
        )
        footer_text = f"Catalog restocks daily (Day {next_day}). Tap Close Store to exit."
    elif merchant.get("is_faction_quartermaster"):
        embed = discord.Embed(
            title=f"🎖️ {merchant.get('flavor_name') or 'Faction Quartermaster'}",
            description=merchant.get("intro_narrative", ""),
            color=discord.Color.gold()
        )
        footer_text = f"Member-exclusive stock. Wares restock daily (Day {next_day})."
    else:
        embed = discord.Embed(
            title=f"{arch_emoji} {merchant.get('flavor_name') or arch_title}",
            description=merchant.get("intro_narrative", ""),
            color=discord.Color.dark_gold()
        )
        footer_text = f"Wares restock daily (Day {next_day}). Buy/Sell any time."

    if merchant.get("faction_discount_pct"):
        embed.add_field(name="Faction Standing", value=f"{merchant['faction_discount_pct']}% off", inline=True)
    if merchant.get("discount_pct"):
        embed.add_field(name="Haggle Discount", value=f"{merchant['discount_pct']}%", inline=True)
    embed.add_field(name="Haggle Attempts Left", value=f"{3 - merchant.get('haggle_attempts', 0)}/3", inline=True)
    embed.add_field(name="🕒 Daily Restock", value=f"Start of **Day {next_day}**", inline=True)
    if extra_note:
        embed.add_field(name="Update", value=extra_note, inline=False)
    embed.set_footer(text=footer_text)
    return embed


class BazaarStoreSelectDropdown(discord.ui.Select):
    def __init__(self, cog: "AdventureCog", session_id: int, available_stores: list[dict]):
        self.cog = cog
        self.session_id = session_id
        options = []
        for store in available_stores[:25]:
            options.append(discord.SelectOption(
                label=store["title"][:100],
                value=store["type"],
                description=store.get("description", "")[:100],
                emoji=store.get("emoji", "🛍️")
            ))
        super().__init__(placeholder="Choose a shop or merchant stall to visit...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        selected_type = self.values[0]
        await self.cog.enter_merchant_shop(
            interaction,
            self.session_id,
            initiator_id=interaction.user.id,
            merchant_type=selected_type
        )


class BazaarStoreSelectView(discord.ui.View):
    def __init__(self, cog: "AdventureCog", session_id: int, available_stores: list[dict]):
        super().__init__(timeout=180)
        self.cog = cog
        self.session_id = session_id
        self.add_item(BazaarStoreSelectDropdown(cog, session_id, available_stores))


async def handle_talk_to_merchant(cog: "AdventureCog", session_id: int, interaction: discord.Interaction):
    session = db.get_session(session_id)
    if interaction.user.id not in session["turn_order"]:
        await interaction.response.send_message("You're not part of this adventure.", ephemeral=True)
        return

    scen_key = session.get("scenario", "fantasy")
    current_loc = session.get("current_location", "")
    from mechanics.world.locations import get_available_merchant_types_for_location
    available_stores = get_available_merchant_types_for_location(current_loc, scen_key=scen_key)

    if len(available_stores) > 1:
        view = BazaarStoreSelectView(cog, session_id, available_stores)
        await interaction.response.send_message(
            f"🏛️ **Marketplace Directory — {current_loc}**\nSelect a specialist shop or stall to browse their wares:",
            view=view,
            ephemeral=True
        )
        return

    single_type = available_stores[0]["type"] if available_stores else "general_merchant"

    if len(session["turn_order"]) <= 1:
        await cog.enter_merchant_shop(interaction, session_id, initiator_id=interaction.user.id, merchant_type=single_type)
        return

    merchant = session["merchant"]
    prompt = f"**{merchant.get('flavor_name') or 'A merchant'}** is nearby. Approach them?"

    async def on_unanimous(vote_interaction: discord.Interaction):
        await cog.enter_merchant_shop(vote_interaction, session_id, initiator_id=interaction.user.id, merchant_type=single_type)

    async def on_not_unanimous(vote_interaction: discord.Interaction):
        await cog.attempt_merchant_detour(vote_interaction, session_id, initiator_id=interaction.user.id)

    vote_view = MerchantVoteView(cog, session_id, session["turn_order"], prompt, on_unanimous, on_not_unanimous)
    await interaction.response.edit_message(content=prompt, embed=None, view=vote_view)


class MerchantVoteView(discord.ui.View):
    def __init__(self, cog: "AdventureCog", session_id: int, member_ids: list, prompt: str,
                 on_unanimous, on_not_unanimous):
        super().__init__(timeout=120)
        self.cog = cog
        self.session_id = session_id
        self.member_ids = member_ids
        self.prompt = prompt
        self.on_unanimous = on_unanimous
        self.on_not_unanimous = on_not_unanimous
        self.votes = {}

        yes = discord.ui.Button(label="Yes", emoji="✅", style=discord.ButtonStyle.success)
        yes.callback = self._make_vote_callback(True)
        self.add_item(yes)
        no = discord.ui.Button(label="No", emoji="❌", style=discord.ButtonStyle.danger)
        no.callback = self._make_vote_callback(False)
        self.add_item(no)

    def _make_vote_callback(self, value: bool):
        async def _callback(interaction: discord.Interaction):
            if interaction.user.id not in self.member_ids:
                await interaction.response.send_message("You're not part of this party.", ephemeral=True)
                return
            if interaction.user.id in self.votes:
                await interaction.response.send_message("You've already voted.", ephemeral=True)
                return
            self.votes[interaction.user.id] = value

            if value is False:
                self.stop()
                await self.on_not_unanimous(interaction)
                return

            remaining = [uid for uid in self.member_ids if uid not in self.votes]
            if remaining:
                mentions = ", ".join(f"<@{uid}>" for uid in remaining)
                await interaction.response.edit_message(content=f"{self.prompt}\n\nWaiting on: {mentions}",
                                                          view=self)
                return

            self.stop()
            await self.on_unanimous(interaction)
        return _callback

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True


class BuySelectView(discord.ui.View):
    def __init__(
        self,
        cog: "AdventureCog",
        session_id: int,
        stock: list,
        discount_pct: int,
        shop_ctx: dict | None = None,
    ):
        super().__init__(timeout=180)
        self.cog = cog
        self.session_id = session_id
        options = []
        seen_values = set()
        for idx, item in enumerate(stock[:25]):
            price = compute_effective_shop_item_price(item, shop_ctx=shop_ctx, discount_pct=discount_pct)
            t = item.get("tier", 3)
            badge = "⚪" if t == 3 else ("🔷" if t == 2 else "👑")
            name = str(item.get("name", "Item"))[:60]
            val = name[:100]
            if val in seen_values:
                val = f"{name[:85]} #{idx+1}"[:100]
            seen_values.add(val)
            desc = (item.get("description") or "").strip()[:100] or None
            qty = item.get("quantity", 1)
            options.append(discord.SelectOption(
                label=f"{badge} {name} — {price}g (x{qty} left)"[:100],
                value=val,
                description=desc,
            ))
        select = discord.ui.Select(placeholder="Choose an item to buy...", options=options)
        select.callback = self._on_select
        self.add_item(select)

    async def _on_select(self, interaction: discord.Interaction):
        item_name = interaction.data["values"][0]
        await self.cog.buy_item(interaction, self.session_id, interaction.user.id, item_name)


class SellSelectView(discord.ui.View):
    def __init__(self, cog: "AdventureCog", session_id: int, priced_items: list):
        super().__init__(timeout=180)
        self.cog = cog
        self.session_id = session_id
        self.priced_by_id = {str(i["id"]): i for i in priced_items}
        options = [
            discord.SelectOption(label=f"{i['name']} — {i['price']}g"[:100], value=str(i["id"]))
            for i in priced_items[:25]
        ]
        select = discord.ui.Select(placeholder="Choose an item to sell...", options=options)
        select.callback = self._on_select
        self.add_item(select)

    async def _on_select(self, interaction: discord.Interaction):
        item_id = interaction.data["values"][0]
        entry = self.priced_by_id.get(item_id)
        if not entry:
            await interaction.response.send_message("That item is no longer available.", ephemeral=True)
            return
        await self.cog.sell_item(interaction, self.session_id, interaction.user.id,
                                  int(item_id), entry["name"], entry["price"])


class RumorView(discord.ui.View):
    def __init__(self, cog: "AdventureCog", session_id: int, rumors: list):
        super().__init__(timeout=300)
        self.cog = cog
        self.session_id = session_id
        for idx, rumor in enumerate(rumors[:3]):
            revealed = bool(rumor.get("revealed"))
            label = f"Rumor {idx + 1}" + (" (known)" if revealed else "")
            button = discord.ui.Button(label=label, emoji="👂", style=discord.ButtonStyle.secondary,
                                        disabled=revealed, row=0)
            button.callback = self._make_callback(idx)
            self.add_item(button)
        back = discord.ui.Button(label="Back to Shop", emoji="🔙", style=discord.ButtonStyle.primary, row=1)
        back.callback = self._on_back
        self.add_item(back)

    def _make_callback(self, idx: int):
        async def _callback(interaction: discord.Interaction):
            await self.cog.reveal_rumor(interaction, self.session_id, interaction.user.id, idx)
        return _callback

    async def _on_back(self, interaction: discord.Interaction):
        await self.cog.return_to_merchant_view(interaction, self.session_id)


class MerchantView(discord.ui.View):
    def __init__(self, cog: "AdventureCog", session_id: int, member_ids: list, is_phone_shop: bool = None):
        super().__init__(timeout=1800)
        self.cog = cog
        self.session_id = session_id
        self.member_ids = member_ids

        if is_phone_shop is None:
            sess = db.get_session(session_id)
            is_phone_shop = bool(sess and sess.get("merchant", {}).get("is_phone_shop"))
        self.is_phone_shop = is_phone_shop

        buy = discord.ui.Button(label="Buy", emoji="🛒", style=discord.ButtonStyle.success)
        buy.callback = self._on_buy
        self.add_item(buy)

        sell = discord.ui.Button(label="Sell", emoji="💰", style=discord.ButtonStyle.primary)
        sell.callback = self._on_sell
        self.add_item(sell)

        haggle = discord.ui.Button(label="Haggle", emoji="🤝", style=discord.ButtonStyle.secondary)
        haggle.callback = self._on_haggle
        self.add_item(haggle)

        if not self.is_phone_shop:
            ask = discord.ui.Button(label="Ask", emoji="👂", style=discord.ButtonStyle.secondary)
            ask.callback = self._on_ask
            self.add_item(ask)

        leave_label = "Close Store" if self.is_phone_shop else "Leave"
        leave = discord.ui.Button(label=leave_label, emoji="🚪", style=discord.ButtonStyle.danger)
        leave.callback = self._on_leave
        self.add_item(leave)

    def _in_party(self, user_id: int) -> bool:
        return user_id in self.member_ids

    async def _collective_action(self, interaction: discord.Interaction, action_label: str, on_execute):
        if len(self.member_ids) <= 1:
            await on_execute(interaction)
            return
        char = db.get_character(interaction.user.id)
        prompt = f"**{char['name']}** wants to {action_label}. Does everyone agree?"

        async def on_not_unanimous(vote_interaction: discord.Interaction):
            await self.cog._merchant_consensus_failed(vote_interaction, self.session_id, action_label)

        vote_view = MerchantVoteView(self.cog, self.session_id, self.member_ids, prompt,
                                      on_execute, on_not_unanimous)
        await interaction.response.send_message(content=prompt, view=vote_view)

    async def _on_buy(self, interaction: discord.Interaction):
        if not self._in_party(interaction.user.id):
            await interaction.response.send_message("You're not part of this adventure.", ephemeral=True)
            return
        await self.cog.open_buy_menu(interaction, self.session_id)

    async def _on_sell(self, interaction: discord.Interaction):
        if not self._in_party(interaction.user.id):
            await interaction.response.send_message("You're not part of this adventure.", ephemeral=True)
            return
        await self.cog.open_sell_menu(interaction, self.session_id)

    async def _on_haggle(self, interaction: discord.Interaction):
        if not self._in_party(interaction.user.id):
            await interaction.response.send_message("You're not part of this adventure.", ephemeral=True)
            return
        initiator_id = interaction.user.id

        async def execute(vote_interaction: discord.Interaction):
            await self.cog.resolve_haggle(vote_interaction, self.session_id, initiator_id)

        await self._collective_action(interaction, "haggle with the merchant", execute)

    async def _on_ask(self, interaction: discord.Interaction):
        if not self._in_party(interaction.user.id):
            await interaction.response.send_message("You're not part of this adventure.", ephemeral=True)
            return

        async def execute(vote_interaction: discord.Interaction):
            await self.cog._show_rumor_menu(vote_interaction, self.session_id)

        await self._collective_action(interaction, "ask around for rumors", execute)

    async def _on_leave(self, interaction: discord.Interaction):
        if not self._in_party(interaction.user.id):
            await interaction.response.send_message("You're not part of this adventure.", ephemeral=True)
            return

        async def execute(vote_interaction: discord.Interaction):
            await self.cog.leave_merchant(vote_interaction, self.session_id)

        await self._collective_action(interaction, "leave the shop", execute)
