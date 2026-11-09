from __future__ import annotations
import json
import logging
import random
import re
import time
import discord
from discord import app_commands
import db
import scenario_data
from llm_client import call_llm_json
log = logging.getLogger("hikayat.phone")
from skill_check import resolve_check, success_chance, CheckResult

from .embeds import (
    build_media_gallery_embed,
    build_phone_home_embed,
    get_phone_branding,
    _build_media_item_detail_embed,
    _build_dm_chat_embed,
    _build_gossip_feed_embed,
    _build_social_profile_embed,
)
from .messaging import *

class PhoneOwnerRestrictedView(discord.ui.View):
    """Base phone view enforcing strict device ownership (fail-closed) without Layer-4 imports."""
    user_id: int | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not self.user_id or int(interaction.user.id) != int(self.user_id):
            if interaction.response.is_done() is not True:
                await interaction.response.send_message(
                    "This smartphone belongs to another player.",
                    ephemeral=True,
                )
            return False
        return True


class PhoneMainView(PhoneOwnerRestrictedView):
    """The Home Screen of the Smartphone / Cyberdeck Hub."""
    def __init__(self, cog, session_id: int, user_id: int, *, session: dict | None = None):
        super().__init__(timeout=300)
        self.cog = cog
        self.session_id = session_id
        self.user_id = user_id

        session_obj = session if isinstance(session, dict) else db.get_session(session_id)
        scen_key = session_obj.get("scenario", "fantasy") if session_obj else "fantasy"
        branding = get_phone_branding(scen_key)

        contacts_app = branding.get("contacts_app_name", "Contacts")
        gallery_app = branding.get("gallery_app_name", "Photo Vault")
        gallery_emoji = branding.get("gallery_emoji", "📸")

        contacts_btn = discord.ui.Button(label=contacts_app, emoji="👥", style=discord.ButtonStyle.primary, row=0)
        dm_btn = discord.ui.Button(label=branding["dm_app_name"], emoji="💬", style=discord.ButtonStyle.primary, row=0)
        feed_btn = discord.ui.Button(label=branding["feed_app_name"], emoji=branding["feed_emoji"], style=discord.ButtonStyle.secondary, row=0)
        gallery_btn = discord.ui.Button(label=gallery_app, emoji=gallery_emoji, style=discord.ButtonStyle.secondary, row=0)

        from mechanics.world.locations import is_anomalous_realty_scenario

        bounty_btn = discord.ui.Button(label=branding["bounty_app_name"], emoji="📋", style=discord.ButtonStyle.secondary, row=1)
        shop_btn = discord.ui.Button(label=branding["shop_app_name"], emoji="🛍️", style=discord.ButtonStyle.secondary, row=1)
        encyclopedia_btn = discord.ui.Button(label="Encyclopedia", emoji="📖", style=discord.ButtonStyle.secondary, row=1)
        realty_btn = None
        if is_anomalous_realty_scenario(scen_key):
            from localization import get_realty_label
            _u_lang = _resolve_phone_ui_lang(user_id, session_obj)
            realty_btn = discord.ui.Button(
                label=get_realty_label("app_name", _u_lang)[:80],
                emoji="🏠",
                style=discord.ButtonStyle.success,
                row=1,
            )
            realty_btn.callback = self._open_realty
        close_btn = discord.ui.Button(label="Lock Screen", emoji="🔒", style=discord.ButtonStyle.secondary, row=1)

        contacts_btn.callback = self._open_contacts
        dm_btn.callback = self._open_dms
        feed_btn.callback = self._open_feed
        gallery_btn.callback = self._open_gallery
        bounty_btn.callback = self._open_bounties
        shop_btn.callback = self._open_shop
        encyclopedia_btn.callback = self._open_encyclopedia
        close_btn.callback = self._close_phone

        self.add_item(contacts_btn)
        self.add_item(dm_btn)
        self.add_item(feed_btn)
        self.add_item(gallery_btn)
        self.add_item(bounty_btn)
        self.add_item(shop_btn)
        self.add_item(encyclopedia_btn)
        if realty_btn is not None:
            self.add_item(realty_btn)
        self.add_item(close_btn)

    async def _open_realty(self, interaction: discord.Interaction):
        from mechanics.world.locations.residences import build_realty_payload

        def _prep_realty():
            pl = build_realty_payload(self.session_id, self.user_id)
            lang = _resolve_phone_ui_lang(self.user_id)
            return pl, lang

        payload, lang = await db.adb(_prep_realty)
        embed = _build_realty_embed(payload, lang=lang)
        view = PhoneRealtyView(self.cog, self.session_id, self.user_id, payload, lang=lang)
        await interaction.response.edit_message(embed=embed, view=view)

    async def _open_encyclopedia(self, interaction: discord.Interaction):
        from cogs.contacts import build_folklore_encyclopedia_embed, FolkloreEncyclopediaView
        from mechanics.world.folklore_codex import build_encyclopedia_payload

        settings = await db.adb(db.get_settings, self.user_id)
        ui_lang = (settings or {}).get("ui_language") if isinstance(settings, dict) else None
        payload = await db.adb(
            build_encyclopedia_payload,
            session_id=self.session_id,
            user_id=self.user_id,
            lang=ui_lang,
        )
        embed, _, _ = build_folklore_encyclopedia_embed(payload, mode="archive", tradition_key="all", page=0)
        view = FolkloreEncyclopediaView(
            payload=payload,
            user_id=self.user_id,
            session_id=self.session_id,
            cog=self.cog,
            from_phone=True,
        )
        await interaction.response.edit_message(embed=embed, view=view)

    async def _open_gallery(self, interaction: discord.Interaction):
        def _prep_gallery():
            emb = build_media_gallery_embed(self.session_id, self.user_id, filter_contact=None, filter_type=None, page=0)
            inv = db.get_inventory(self.user_id) if self.user_id else []
            return emb, inv

        embed, inv_items = await db.adb(_prep_gallery)
        view = PhoneMediaGalleryView(
            self.cog,
            self.session_id,
            self.user_id,
            filter_contact=None,
            filter_type=None,
            page=0,
            inv_items=inv_items,
        )
        await interaction.response.edit_message(embed=embed, view=view)

    async def _open_contacts(self, interaction: discord.Interaction):
        char = await db.adb(db.get_character, self.user_id)
        contacts = (await db.adb(db.get_contacts, self.session_id, character_id=char.get("id", 0))) if char else []
        session = await db.adb(db.get_session, self.session_id)
        scen_key = session.get("scenario", "fantasy") if session else "fantasy"
        branding = get_phone_branding(scen_key)

        if not contacts:
            await interaction.response.send_message(
                f"{branding['emoji']} **No contacts saved in your phone yet!**\nMeet and talk to NPCs in the story to exchange contact info.",
                ephemeral=True
            )
            return

        from cogs.contacts import build_contact_list_embed, ContactView
        char_name = char.get("name", "Hero") if char else "Player"
        embed = build_contact_list_embed(contacts, scen_key, char_name)
        view = ContactView(contacts, scen_key, self.user_id, session_id=self.session_id, cog=self.cog, from_phone=True)
        await interaction.response.edit_message(embed=embed, view=view)

    async def _open_dms(self, interaction: discord.Interaction):
        char = await db.adb(db.get_character, self.user_id)
        contacts = (await db.adb(db.get_contacts, self.session_id, character_id=char.get("id", 0))) if char else []
        session = await db.adb(db.get_session, self.session_id)
        scen_key = session.get("scenario", "fantasy") if session else "fantasy"
        branding = get_phone_branding(scen_key)

        if not contacts:
            await interaction.response.send_message(
                f"{branding['emoji']} **No contacts saved in your phone yet!**\nMeet and talk to NPCs in the story to exchange contact info.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title=f"{branding['emoji']} {branding['dm_app_name']} — Select a Contact",
            description=f"Pick a contact below to text, flirt, or ask for investigation clues:",
            color=branding["color"]
        )
        view = DMContactSelectView(self.cog, self.session_id, self.user_id, contacts)
        await interaction.response.edit_message(embed=embed, view=view)

    async def _open_feed(self, interaction: discord.Interaction):
        await interaction.response.defer()
        session = await db.adb(db.get_session, self.session_id)
        scen_key = session.get("scenario", "fantasy") if session else "fantasy"
        branding = get_phone_branding(scen_key)

        posts = await generate_gossip_feed_posts(session)
        state_summary = await db.adb(get_social_state_summary, self.session_id, session)
        embed = _build_gossip_feed_embed(session, posts, branding, charges=state_summary["charges"])
        view = SocialFeedView(
            self.cog,
            self.session_id,
            self.user_id,
            posts,
            session=session,
            state_summary=state_summary,
        )
        await interaction.followup.edit_message(message_id=interaction.message.id, embed=embed, view=view)

    async def _open_bounties(self, interaction: discord.Interaction):
        from game_engine import generate_bounty_board
        from cogs.adventure import _build_bounty_board_embed, BountyBoardView
        await interaction.response.defer()
        session = await db.adb(db.get_session, self.session_id)
        bounties = await generate_bounty_board(session)
        embed = _build_bounty_board_embed(session, bounties)
        view = BountyBoardView(session, bounties)
        await interaction.followup.edit_message(message_id=interaction.message.id, embed=embed, view=view)

    async def _open_shop(self, interaction: discord.Interaction):
        await self.cog.enter_merchant_shop(
            interaction,
            self.session_id,
            self.user_id,
            is_phone_shop=True
        )

    async def _close_phone(self, interaction: discord.Interaction):
        await interaction.response.send_message("📱 Phone screen locked.", ephemeral=True)

class DMContactSelectView(PhoneOwnerRestrictedView):
    """Dropdown menu to select which NPC to message."""
    def __init__(self, cog, session_id: int, user_id: int, contacts: list[dict]):
        super().__init__(timeout=300)
        self.cog = cog
        self.session_id = session_id
        self.user_id = user_id
        self.contacts_dict = {c["npc_id"]: c for c in contacts}

        options = []
        for c in contacts[:25]:
            name = c.get("name", "Unknown")
            score = c.get("relationship_score", 0)
            track = c.get("track", "platonic").capitalize()
            role = c.get("basic_info", {}).get("role") or c.get("basic_info", {}).get("occupation") or "Contact"
            score_sign = f"+{score}" if score > 0 else str(score)
            options.append(discord.SelectOption(
                label=f"{name} ({score_sign})",
                description=f"{role} • Track: {track}"[:100],
                value=c["npc_id"],
                emoji="💬"
            ))

        select = discord.ui.Select(placeholder="Choose who to message...", options=options)
        select.callback = self._on_select_contact
        self.add_item(select)

        back_btn = discord.ui.Button(label="Phone Home", emoji="📱", style=discord.ButtonStyle.secondary)
        back_btn.callback = self._back_to_home
        self.add_item(back_btn)

    async def _on_select_contact(self, interaction: discord.Interaction):
        npc_id = interaction.data["values"][0]
        contact = self.contacts_dict.get(npc_id)
        if not contact:
            await interaction.response.send_message("Contact not found.", ephemeral=True)
            return

        def _prep_dm_chat():
            emb = _build_dm_chat_embed(self.session_id, contact)
            sess = db.get_session(self.session_id)
            return emb, sess

        embed, session = await db.adb(_prep_dm_chat)
        view = DMChatView(self.cog, self.session_id, self.user_id, contact, list(self.contacts_dict.values()), session=session)
        await interaction.response.edit_message(embed=embed, view=view)

    async def _back_to_home(self, interaction: discord.Interaction):
        def _prep_home():
            emb = build_phone_home_embed(self.session_id, self.user_id)
            sess = db.get_session(self.session_id)
            return emb, sess

        embed, session = await db.adb(_prep_home)
        view = PhoneMainView(self.cog, self.session_id, self.user_id, session=session)
        await interaction.response.edit_message(embed=embed, view=view)

class DMChatView(PhoneOwnerRestrictedView):
    """Active chat view with a specific contact."""
    def __init__(self, cog, session_id: int, user_id: int, contact: dict, all_contacts: list[dict], *, session: dict | None = None):
        super().__init__(timeout=300)
        self.cog = cog
        self.session_id = session_id
        self.user_id = user_id
        self.contact = contact
        self.all_contacts = all_contacts

        session_obj = session if isinstance(session, dict) else db.get_session(session_id)
        scen_key = session_obj.get("scenario", "fantasy") if session_obj else "fantasy"
        is_nsfw = scenario_data.is_nsfw_scenario(scen_key)
        is_romantic = str(contact.get("track", "platonic")).lower() == "romantic"

        # Row 0: Social & Romance
        chat_btn = discord.ui.Button(label="Have a Chat", emoji="💬", style=discord.ButtonStyle.primary, row=0)
        flirt_btn = discord.ui.Button(label="Flirt & Tease", emoji="💌", style=discord.ButtonStyle.success, row=0)
        if is_romantic:
            meet_btn = discord.ui.Button(label="Ask Out for a Date", emoji="🌹", style=discord.ButtonStyle.secondary, row=0)
        else:
            meet_btn = discord.ui.Button(label="Ask to Meet Up", emoji="📍", style=discord.ButtonStyle.secondary, row=0)
        photo_btn = discord.ui.Button(label="Exchange Photos", emoji="📸", style=discord.ButtonStyle.secondary, row=0)

        chat_btn.callback = self._quick_chat
        flirt_btn.callback = self._quick_flirt
        meet_btn.callback = self._quick_meet
        photo_btn.callback = self._quick_photo

        self.add_item(chat_btn)
        self.add_item(flirt_btn)
        self.add_item(meet_btn)
        self.add_item(photo_btn)

        if is_nsfw:
            nsfw_photo_btn = discord.ui.Button(label="Swap Intimate Photos", emoji="🔞", style=discord.ButtonStyle.danger, row=0)
            nsfw_photo_btn.callback = self._quick_nsfw_photo
            self.add_item(nsfw_photo_btn)

        # Row 1: Intel & Actions
        intel_rumor_btn = discord.ui.Button(label="Intel & Rumors", emoji="🔍", style=discord.ButtonStyle.primary, row=1)
        type_btn = discord.ui.Button(label="Type Custom Message", emoji="✏️", style=discord.ButtonStyle.secondary, row=1)
        back_btn = discord.ui.Button(label="Contacts", emoji="🔙", style=discord.ButtonStyle.secondary, row=1)

        intel_rumor_btn.callback = self._quick_intel_rumor
        type_btn.callback = self._open_custom_modal
        back_btn.callback = self._back_to_contacts

        self.add_item(intel_rumor_btn)
        self.add_item(type_btn)
        self.add_item(back_btn)

    async def _quick_chat(self, interaction: discord.Interaction):
        await self._send_dm_action(interaction, None, intent="chat")

    async def _quick_flirt(self, interaction: discord.Interaction):
        await self._send_dm_action(interaction, None, intent="flirt")

    async def _quick_meet(self, interaction: discord.Interaction):
        await self._send_dm_action(interaction, None, intent="meetup")

    async def _quick_photo(self, interaction: discord.Interaction):
        def _load_photo_ctx():
            return db.get_character(self.user_id), db.get_session(self.session_id)

        char, session = await db.adb(_load_photo_ctx)
        loc = session.get("current_location", "around here") if session else "around here"
        caption = generate_player_photo_caption(char, intent="photo", location=loc)
        msg = f"Sending you a quick snapshot from {loc}! 📸\n[Attached Photo: {caption}]\nWhat are you up to right now?"
        await self._send_dm_action(interaction, msg, intent="photo")

    async def _quick_nsfw_photo(self, interaction: discord.Interaction):
        char = await db.adb(db.get_character, self.user_id)
        caption = generate_player_photo_caption(char, intent="nsfw_photo")
        msg = f"Sending an intimate selfie just for your eyes... 🔞\n[Attached Intimate Photo: {caption}]\nHope you like what you see 😉"
        await self._send_dm_action(interaction, msg, intent="nsfw_photo")

    async def _quick_intel_rumor(self, interaction: discord.Interaction):
        npc_id = self.contact.get("npc_id") or self.contact["name"].lower().replace(" ", "_")
        history_rows = await db.adb(db.get_phone_messages, self.session_id, npc_id, 2)
        if history_rows:
            msg = "By the way, what's the latest word around here? Heard anything interesting or any rumors lately? 🔍"
        else:
            msg = "Hey, what's the latest word around here? Heard anything interesting or any rumors lately? 🔍"
        await self._send_dm_action(interaction, msg, intent="intel_rumor")

    async def _open_custom_modal(self, interaction: discord.Interaction):
        modal = DMCustomMessageModal(self.cog, self.session_id, self.user_id, self.contact, self)
        await interaction.response.send_modal(modal)

    async def _send_dm_action(self, interaction: discord.Interaction, message_text: str = None, intent: str = "chat"):
        await interaction.response.defer()

        def _load_dm_ctx():
            return db.get_character(self.user_id), db.get_session(self.session_id)

        char, session = await db.adb(_load_dm_ctx)

        if not message_text:
            message_text = await generate_player_chat_message(session, self.contact, char, intent=intent)

        reply_data = await generate_contact_dm_reply(session, self.contact, char, message_text, intent=intent)

        # Refresh contact data with new score
        npc_id = self.contact.get("npc_id") or self.contact["name"].lower().replace(" ", "_")

        def _refresh_dm_embed():
            upd = db.get_contact(self.session_id, npc_id, character_id=char.get("id", 0) if char else 0) or self.contact
            emb = _build_dm_chat_embed(self.session_id, upd, last_reply=reply_data)
            return upd, emb

        updated_contact, embed = await db.adb(_refresh_dm_embed)
        self.contact = updated_contact
        await interaction.followup.edit_message(message_id=interaction.message.id, embed=embed, view=self)

    async def _back_to_contacts(self, interaction: discord.Interaction):
        session = await db.adb(db.get_session, self.session_id)
        scen_key = session.get("scenario", "fantasy") if session else "fantasy"
        branding = get_phone_branding(scen_key)
        embed = discord.Embed(
            title=f"{branding['emoji']} {branding['dm_app_name']} — Select a Contact",
            description=f"Pick a contact below to text, flirt, or ask for investigation clues:",
            color=branding["color"]
        )
        view = DMContactSelectView(self.cog, self.session_id, self.user_id, self.all_contacts)
        await interaction.response.edit_message(embed=embed, view=view)

class DMCustomMessageModal(discord.ui.Modal):
    def __init__(self, cog, session_id: int, user_id: int, contact: dict, chat_view: DMChatView):
        contact_name = contact.get("name", "Contact")
        super().__init__(title=f"Text to {contact_name[:20]}")
        self.cog = cog
        self.session_id = session_id
        self.user_id = user_id
        self.contact = contact
        self.chat_view = chat_view

        self.msg_input = discord.ui.TextInput(
            label="Your Message",
            style=discord.TextStyle.paragraph,
            placeholder=f"Type what you want to text {contact_name}...",
            max_length=250,
            required=True
        )
        self.add_item(self.msg_input)

    async def on_submit(self, interaction: discord.Interaction):
        user_text = str(self.msg_input.value).strip()
        await self.chat_view._send_dm_action(interaction, user_text, intent="custom")

class SocialFeedView(PhoneOwnerRestrictedView):
    """View displaying social timeline posts with single rumor scouring and character discovery buttons."""
    def __init__(
        self,
        cog,
        session_id: int,
        user_id: int,
        posts: list[dict],
        *,
        session: dict | None = None,
        state_summary: dict | None = None,
    ):
        super().__init__(timeout=300)
        self.cog = cog
        self.session_id = session_id
        self.user_id = user_id
        self.posts = posts

        session_obj = session if isinstance(session, dict) else db.get_session(session_id)
        summary_obj = state_summary if isinstance(state_summary, dict) else get_social_state_summary(session_id, session_obj)
        charges = summary_obj["charges"]

        # Row 0: Investigation & Social Discovery
        rumor_btn = discord.ui.Button(
            label=f"Dig for Rumors ({charges}/3)",
            emoji="🔍",
            style=discord.ButtonStyle.primary,
            row=0
        )
        search_btn = discord.ui.Button(
            label="Search User",
            emoji="🔎",
            style=discord.ButtonStyle.secondary,
            row=0
        )
        find_btn = discord.ui.Button(
            label="Find Friends",
            emoji="✨",
            style=discord.ButtonStyle.secondary,
            row=0
        )

        rumor_btn.callback = self._dig_rumors
        search_btn.callback = self._search_user
        find_btn.callback = self._find_friends

        self.add_item(rumor_btn)
        self.add_item(search_btn)
        self.add_item(find_btn)

        # Row 1: Refresh & Navigation
        refresh_btn = discord.ui.Button(label="Refresh Feed", emoji="🔄", style=discord.ButtonStyle.secondary, row=1)
        world_pulse_btn = discord.ui.Button(label="World Pulse", emoji="🌐", style=discord.ButtonStyle.secondary, row=1)
        world_pulse_btn.callback = self._open_world_pulse
        self.add_item(world_pulse_btn)
        back_btn = discord.ui.Button(label="Phone Home", emoji="📱", style=discord.ButtonStyle.secondary, row=1)

        refresh_btn.callback = self._refresh_feed
        back_btn.callback = self._back_to_home

        self.add_item(refresh_btn)
        self.add_item(back_btn)

    async def _dig_rumors(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        session = await db.adb(db.get_session, self.session_id)
        res = await scour_feed_for_rumor(session, self.user_id)

        if res.get("error") == "exhausted":
            await interaction.followup.send(res["message"], ephemeral=True)
            return

        check = res.get("check")
        tier_emoji = {
            "crit_success": "⭐⭐",
            "success": "🎯",
            "fail": "❌",
            "crit_fail": "💀"
        }.get(check.get("tier"), "🎲") if check else "🎲"

        if res.get("success"):
            embed = discord.Embed(
                title="🔍 Verified Rumor Clue Discovered!",
                description=f"🎲 **{check['stat']} Investigation Check ({check['chance']}%)**: {tier_emoji} **{check['tier_label']}**\n\n"
                            f"📰 **Lead:** *\"{res['clue']}\"*\n"
                            f"📡 **Source:** `{res.get('source', 'Social Feed')}`\n\n"
                            f"📁 *Saved to your `/quest` Case File!*",
                color=discord.Color.green()
            )
            embed.set_footer(text=f"Rumor Searches Left: {res.get('charges_left', 0)}/3 (Resets every 5 turns)")
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            embed = discord.Embed(
                title="❌ Feed Noise / Dead End",
                description=f"🎲 **{check['stat']} Investigation Check ({check['chance']}%)**: {tier_emoji} **{check['tier_label']}**\n\n"
                            f"💬 *\"{res['red_herring']}\"*\n\n"
                            f"⚠️ *No actionable quest clues extracted.*",
                color=discord.Color.dark_grey()
            )
            embed.set_footer(text=f"Rumor Searches Left: {res.get('charges_left', 0)}/3 (Resets every 5 turns)")
            await interaction.followup.send(embed=embed, ephemeral=True)

    async def _search_user(self, interaction: discord.Interaction):
        modal = SocialSearchModal(self.cog, self.session_id, self.user_id, self)
        await interaction.response.send_modal(modal)

    async def _find_friends(self, interaction: discord.Interaction):
        await interaction.response.defer()

        def _prep_find():
            sess = db.get_session(self.session_id)
            scen_k = sess.get("scenario", "fantasy") if sess else "fantasy"
            br = get_phone_branding(scen_k)
            prof = discover_suggested_peer(self.session_id, self.user_id)
            emb = _build_social_profile_embed(self.session_id, prof, br) if prof else None
            return prof, emb

        profile, embed = await db.adb(_prep_find)
        if not profile:
            await interaction.followup.send("⚠️ No student profiles available right now.", ephemeral=True)
            return

        view = SocialProfileView(self.cog, self.session_id, self.user_id, profile, self.posts)
        await interaction.followup.edit_message(message_id=interaction.message.id, embed=embed, view=view)

    async def _open_world_pulse(self, interaction: discord.Interaction):
        from cogs.adventure.views.world_pulse import WorldPulseView, build_world_pulse_embed
        from mechanics.world.world_events.engine import build_client_world_pulse_payload
        from db import adb
        payload = await adb(build_client_world_pulse_payload, self.session_id)
        embed = build_world_pulse_embed(self.session_id, "all", payload=payload)
        uid = interaction.user.id if getattr(interaction, "user", None) else self.user_id
        view = WorldPulseView(self.session_id, uid, filter_mode="all", payload=payload)
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def _refresh_feed(self, interaction: discord.Interaction):
        await interaction.response.defer()
        session = await db.adb(db.get_session, self.session_id)
        scen_key = session.get("scenario", "fantasy") if session else "fantasy"
        branding = get_phone_branding(scen_key)

        new_posts = await generate_gossip_feed_posts(session, force_refresh=True)
        state_summary = await db.adb(get_social_state_summary, self.session_id, session)
        embed = _build_gossip_feed_embed(session, new_posts, branding, charges=state_summary["charges"])
        view = SocialFeedView(
            self.cog,
            self.session_id,
            self.user_id,
            new_posts,
            session=session,
            state_summary=state_summary,
        )
        await interaction.followup.edit_message(message_id=interaction.message.id, embed=embed, view=view)

    async def _back_to_home(self, interaction: discord.Interaction):
        def _prep_home():
            emb = build_phone_home_embed(self.session_id, self.user_id)
            sess = db.get_session(self.session_id)
            return emb, sess

        embed, session = await db.adb(_prep_home)
        view = PhoneMainView(self.cog, self.session_id, self.user_id, session=session)
        await interaction.response.edit_message(embed=embed, view=view)

class SocialSearchModal(discord.ui.Modal):
    """Modal to search for a character / student by name or handle."""
    def __init__(self, cog, session_id: int, user_id: int, feed_view: SocialFeedView):
        super().__init__(title="Search Social Network")
        self.cog = cog
        self.session_id = session_id
        self.user_id = user_id
        self.feed_view = feed_view

        self.query_input = discord.ui.TextInput(
            label="Name or Handle (@username)",
            placeholder="e.g. Sofia, Justin Anderson, @gamer_girl_99",
            min_length=2,
            max_length=40,
            required=True
        )
        self.add_item(self.query_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        query = str(self.query_input.value).strip()

        def _prep_search():
            prof = lookup_social_profile(self.session_id, self.user_id, query)
            sess = db.get_session(self.session_id)
            scen_k = sess.get("scenario", "fantasy") if sess else "fantasy"
            br = get_phone_branding(scen_k)
            emb = _build_social_profile_embed(self.session_id, prof, br) if prof else None
            return prof, emb

        profile, embed = await db.adb(_prep_search)

        if not profile:
            await interaction.followup.send(
                f"🔎 **No user found:** No matching profile found for **'{query}'** in the network directory.",
                ephemeral=True
            )
            return

        view = SocialProfileView(self.cog, self.session_id, self.user_id, profile, self.feed_view.posts)
        await interaction.followup.edit_message(message_id=interaction.message.id, embed=embed, view=view)

class SocialProfileView(PhoneOwnerRestrictedView):
    """View displaying a faux social media profile with Send Friend Request option."""
    def __init__(self, cog, session_id: int, user_id: int, profile: dict, posts: list[dict]):
        super().__init__(timeout=300)
        self.cog = cog
        self.session_id = session_id
        self.user_id = user_id
        self.profile = profile
        self.posts = posts

        if not profile.get("is_faculty") and not profile.get("is_already_contact"):
            cooldown = profile.get("cooldown_turns_left", 0)
            is_cd = bool(profile.get("on_cooldown") or cooldown > 0)
            if is_cd:
                req_btn = discord.ui.Button(
                    label="Request Pending (Available Tomorrow)",
                    emoji="⏳",
                    style=discord.ButtonStyle.secondary,
                    disabled=True,
                    row=0
                )
            else:
                req_btn = discord.ui.Button(
                    label="Send Friend Request",
                    emoji="➕",
                    style=discord.ButtonStyle.primary,
                    row=0
                )
                req_btn.callback = self._send_request
            self.add_item(req_btn)
        elif profile.get("is_already_contact"):
            dm_btn = discord.ui.Button(
                label="Send Direct Message",
                emoji="💬",
                style=discord.ButtonStyle.success,
                row=0
            )
            dm_btn.callback = self._open_dm_with_contact
            self.add_item(dm_btn)

        back_btn = discord.ui.Button(label="Back to Feed", emoji="🔙", style=discord.ButtonStyle.secondary, row=0)
        back_btn.callback = self._back_to_feed
        self.add_item(back_btn)

    async def _send_request(self, interaction: discord.Interaction):
        def _resolve_req():
            sess = db.get_session(self.session_id)
            r = resolve_social_friend_request(sess, self.user_id, self.profile)
            if r.get("on_cooldown"):
                return sess, r, None, None
            scen_k = sess.get("scenario", "fantasy") if sess else "fantasy"
            br = get_phone_branding(scen_k)
            upd_prof = lookup_social_profile(self.session_id, self.user_id, self.profile["name"]) or self.profile
            emb = _build_social_profile_embed(self.session_id, upd_prof, br)
            return sess, r, upd_prof, emb

        session, res, updated_profile, embed = await db.adb(_resolve_req)

        check = res.get("check") or {}
        tier = check.get("tier") if isinstance(check, dict) else getattr(check, "tier", "fail")
        chance = check.get("chance") if isinstance(check, dict) else getattr(check, "chance", 50)
        tier_label = check.get("tier_label") if isinstance(check, dict) else getattr(check, "tier_label", "Roll")
        stat_name = check.get("stat") if isinstance(check, dict) else getattr(check, "stat", "CHA")
        tier_emoji = {
            "crit_success": "⭐⭐",
            "success": "🎯",
            "fail": "❌",
            "crit_fail": "💀"
        }.get(tier, "🎲")

        if res.get("on_cooldown"):
            await interaction.response.send_message(res["message"], ephemeral=True)
            return

        mod_text = " • ".join(res.get("mod_reasons", [])) or "None"
        msg = (
            f"🎲 **{stat_name} Social Check ({chance}%)**: {tier_emoji} **{tier_label}**\n"
            f"⚡ **Modifiers:** `{mod_text}`\n\n"
            f"{res['message']}"
        )

        view = SocialProfileView(self.cog, self.session_id, self.user_id, updated_profile, self.posts)

        try:
            await interaction.response.edit_message(embed=embed, view=view)
            await interaction.followup.send(msg, ephemeral=True)
        except Exception:
            try:
                await interaction.edit_original_response(embed=embed, view=view)
                await interaction.followup.send(msg, ephemeral=True)
            except Exception:
                try:
                    await interaction.response.send_message(msg, ephemeral=True)
                except Exception:
                    pass

    async def _open_dm_with_contact(self, interaction: discord.Interaction):
        def _prep_dm():
            ch = db.get_character(self.user_id)
            cts = db.get_contacts(self.session_id, character_id=ch.get("id", 0)) if ch else []
            ct = db.get_contact(self.session_id, self.profile["npc_id"], character_id=ch.get("id", 0)) if ch else None
            if not ct:
                return None, [], None, None
            emb = _build_dm_chat_embed(self.session_id, ct)
            sess = db.get_session(self.session_id)
            return ct, cts, emb, sess

        contact, contacts, embed, session = await db.adb(_prep_dm)

        if not contact:
            await interaction.response.send_message("Contact not found.", ephemeral=True)
            return

        view = DMChatView(self.cog, self.session_id, self.user_id, contact, contacts, session=session)
        await interaction.response.edit_message(embed=embed, view=view)

    async def _back_to_feed(self, interaction: discord.Interaction):
        def _prep_feed():
            sess = db.get_session(self.session_id)
            scen_k = sess.get("scenario", "fantasy") if sess else "fantasy"
            br = get_phone_branding(scen_k)
            st = get_social_state_summary(self.session_id, sess)
            emb = _build_gossip_feed_embed(sess, self.posts, br, charges=st["charges"])
            return sess, st, emb

        session, state_summary, embed = await db.adb(_prep_feed)
        view = SocialFeedView(
            self.cog,
            self.session_id,
            self.user_id,
            self.posts,
            session=session,
            state_summary=state_summary,
        )
        await interaction.response.edit_message(embed=embed, view=view)

class PhoneMediaGalleryView(PhoneOwnerRestrictedView):
    """Interactive media album browser with contact filtering, category tags, and pagination."""
    def __init__(
        self,
        cog,
        session_id: int,
        user_id: int,
        filter_contact: str = None,
        filter_type: str = None,
        page: int = 0,
        *,
        inv_items: list[dict] | None = None,
    ):
        super().__init__(timeout=300)
        self.cog = cog
        self.session_id = session_id
        self.user_id = user_id
        self.filter_contact = filter_contact
        self.filter_type = filter_type
        self.page = page

        resolved_inv = inv_items if isinstance(inv_items, list) else (db.get_inventory(user_id) if user_id else [])
        from mechanics.combat.items import is_digital_item, parse_digital_item_metadata
        all_digital = [it for it in resolved_inv if is_digital_item(it)]

        # Unique contacts list
        contacts_seen = []
        for it in all_digital:
            m = parse_digital_item_metadata(it) or {}
            c_name = m.get("contact_name") or ""
            if c_name and c_name not in contacts_seen:
                contacts_seen.append(c_name)

        # Apply Contact filter
        if filter_contact and filter_contact != "ALL":
            filtered = []
            for it in all_digital:
                m = parse_digital_item_metadata(it) or {}
                c_name = m.get("contact_name") or ""
                if c_name.lower() == filter_contact.lower() or filter_contact.lower() in it.get("name", "").lower():
                    filtered.append(it)
        else:
            filtered = all_digital

        # Apply Category filter
        if filter_type:
            ft_low = filter_type.lower()
            cat_filtered = []
            for it in filtered:
                m = parse_digital_item_metadata(it) or {}
                m_type = str(m.get("media_type") or "").lower()
                name_l = it.get("name", "").lower()
                if ft_low == "photos":
                    if "video" not in m_type and "video" not in name_l and "nsfw" not in m_type and "intimate" not in name_l:
                        cat_filtered.append(it)
                elif ft_low == "intimate":
                    if "nsfw" in m_type or "intimate" in m_type or "intimate" in name_l or "🔞" in name_l:
                        cat_filtered.append(it)
                elif ft_low == "videos":
                    if "video" in m_type or "video" in name_l:
                        cat_filtered.append(it)
            filtered = cat_filtered

        page_size = 5
        max_pages = max(1, (len(filtered) + page_size - 1) // page_size)
        self.page = max(0, min(page, max_pages - 1))
        paged_items = filtered[self.page * page_size : (self.page + 1) * page_size]
        self.items_dict = {str(it["id"]): it for it in paged_items if it.get("id")}

        # 1. Item Selection Dropdown
        if paged_items:
            options = []
            for idx, it in enumerate(paged_items, start=self.page * page_size + 1):
                m = parse_digital_item_metadata(it) or {}
                m_type = m.get("media_type") or "photo"
                c_sender = m.get("contact_name") or "Subject"
                icon = "🔞" if "nsfw" in m_type or "intimate" in m_type else ("📹" if "video" in m_type else "📸")
                options.append(discord.SelectOption(
                    label=f"#{idx} {it['name'][:80]}",
                    description=f"From: {c_sender}"[:100],
                    value=str(it["id"]),
                    emoji=icon
                ))
            select_item = discord.ui.Select(placeholder="🔍 View Photo / Video details...", options=options, row=0)
            select_item.callback = self._on_select_item
            self.add_item(select_item)

        # 2. Contact Filter Dropdown (if multiple contacts exist)
        if len(contacts_seen) > 1:
            c_options = [discord.SelectOption(label="All Contacts", value="ALL", default=(not filter_contact or filter_contact == "ALL"))]
            for c_name in contacts_seen[:24]:
                c_options.append(discord.SelectOption(
                    label=c_name[:100],
                    value=c_name,
                    default=(filter_contact == c_name)
                ))
            select_contact = discord.ui.Select(placeholder="Filter by Contact / Subject...", options=c_options, row=1)
            select_contact.callback = self._on_select_contact_filter
            self.add_item(select_contact)

        # 3. Category Buttons
        all_btn = discord.ui.Button(label="All", style=discord.ButtonStyle.primary if not filter_type else discord.ButtonStyle.secondary, row=2)
        photos_btn = discord.ui.Button(label="Photos", emoji="📸", style=discord.ButtonStyle.primary if filter_type == "photos" else discord.ButtonStyle.secondary, row=2)
        intimate_btn = discord.ui.Button(label="Intimate", emoji="🔞", style=discord.ButtonStyle.danger if filter_type == "intimate" else discord.ButtonStyle.secondary, row=2)
        videos_btn = discord.ui.Button(label="Videos", emoji="📹", style=discord.ButtonStyle.primary if filter_type == "videos" else discord.ButtonStyle.secondary, row=2)

        all_btn.callback = self._filter_all
        photos_btn.callback = self._filter_photos
        intimate_btn.callback = self._filter_intimate
        videos_btn.callback = self._filter_videos

        self.add_item(all_btn)
        self.add_item(photos_btn)
        self.add_item(intimate_btn)
        self.add_item(videos_btn)

        # 4. Navigation & Home Buttons
        prev_btn = discord.ui.Button(label="◀️ Prev", style=discord.ButtonStyle.secondary, disabled=(self.page <= 0), row=3)
        next_btn = discord.ui.Button(label="Next ▶️", style=discord.ButtonStyle.secondary, disabled=(self.page >= max_pages - 1), row=3)
        home_btn = discord.ui.Button(label="Phone Home", emoji="📱", style=discord.ButtonStyle.secondary, row=3)

        prev_btn.callback = self._prev_page
        next_btn.callback = self._next_page
        home_btn.callback = self._back_home

        self.add_item(prev_btn)
        self.add_item(next_btn)
        self.add_item(home_btn)

    async def _render_gallery(self, interaction: discord.Interaction, filter_contact: str | None, filter_type: str | None, page: int):
        def _prep():
            emb = build_media_gallery_embed(self.session_id, self.user_id, filter_contact=filter_contact, filter_type=filter_type, page=page)
            inv = db.get_inventory(self.user_id) if self.user_id else []
            return emb, inv

        embed, inv_items = await db.adb(_prep)
        view = PhoneMediaGalleryView(
            self.cog,
            self.session_id,
            self.user_id,
            filter_contact=filter_contact,
            filter_type=filter_type,
            page=page,
            inv_items=inv_items,
        )
        await interaction.response.edit_message(embed=embed, view=view)

    async def _on_select_item(self, interaction: discord.Interaction):
        item_id = interaction.data["values"][0]
        item = self.items_dict.get(item_id)
        if not item:
            inv = (await db.adb(db.get_inventory, self.user_id)) if self.user_id else []
            item = next((it for it in inv if str(it.get("id")) == str(item_id)), None)
        if not item:
            await interaction.response.send_message("Media item not found.", ephemeral=True)
            return
        embed = _build_media_item_detail_embed(item)
        view = PhoneMediaDetailView(self.cog, self.session_id, self.user_id, item, self.filter_contact, self.filter_type, self.page)
        await interaction.response.edit_message(embed=embed, view=view)

    async def _on_select_contact_filter(self, interaction: discord.Interaction):
        chosen = interaction.data["values"][0]
        new_fc = None if chosen == "ALL" else chosen
        await self._render_gallery(interaction, new_fc, self.filter_type, 0)

    async def _filter_all(self, interaction: discord.Interaction):
        await self._render_gallery(interaction, self.filter_contact, None, 0)

    async def _filter_photos(self, interaction: discord.Interaction):
        await self._render_gallery(interaction, self.filter_contact, "photos", 0)

    async def _filter_intimate(self, interaction: discord.Interaction):
        await self._render_gallery(interaction, self.filter_contact, "intimate", 0)

    async def _filter_videos(self, interaction: discord.Interaction):
        await self._render_gallery(interaction, self.filter_contact, "videos", 0)

    async def _prev_page(self, interaction: discord.Interaction):
        await self._render_gallery(interaction, self.filter_contact, self.filter_type, max(0, self.page - 1))

    async def _next_page(self, interaction: discord.Interaction):
        await self._render_gallery(interaction, self.filter_contact, self.filter_type, self.page + 1)

    async def _back_home(self, interaction: discord.Interaction):
        def _prep_home():
            emb = build_phone_home_embed(self.session_id, self.user_id)
            sess = db.get_session(self.session_id)
            return emb, sess

        embed, session = await db.adb(_prep_home)
        view = PhoneMainView(self.cog, self.session_id, self.user_id, session=session)
        await interaction.response.edit_message(embed=embed, view=view)

class PhoneMediaDetailView(PhoneOwnerRestrictedView):
    """View to inspect and manage an individual media item."""
    def __init__(self, cog, session_id: int, user_id: int, item: dict, filter_contact: str = None, filter_type: str = None, page: int = 0):
        super().__init__(timeout=300)
        self.cog = cog
        self.session_id = session_id
        self.user_id = user_id
        self.item = item
        self.filter_contact = filter_contact
        self.filter_type = filter_type
        self.page = page

        back_btn = discord.ui.Button(label="Back to Gallery", emoji="🔙", style=discord.ButtonStyle.secondary, row=0)
        delete_btn = discord.ui.Button(label="Delete Media", emoji="🗑️", style=discord.ButtonStyle.danger, row=0)
        home_btn = discord.ui.Button(label="Phone Home", emoji="📱", style=discord.ButtonStyle.secondary, row=0)

        back_btn.callback = self._back_to_gallery
        delete_btn.callback = self._delete_item
        home_btn.callback = self._back_home

        self.add_item(back_btn)
        self.add_item(delete_btn)
        self.add_item(home_btn)

    async def _back_to_gallery(self, interaction: discord.Interaction):
        def _prep():
            emb = build_media_gallery_embed(self.session_id, self.user_id, self.filter_contact, self.filter_type, self.page)
            inv = db.get_inventory(self.user_id) if self.user_id else []
            return emb, inv

        embed, inv_items = await db.adb(_prep)
        view = PhoneMediaGalleryView(
            self.cog,
            self.session_id,
            self.user_id,
            self.filter_contact,
            self.filter_type,
            self.page,
            inv_items=inv_items,
        )
        await interaction.response.edit_message(embed=embed, view=view)

    async def _delete_item(self, interaction: discord.Interaction):
        item_id = self.item.get("id")

        def _do_delete():
            if item_id:
                db.remove_item(self.user_id, int(item_id))
            emb = build_media_gallery_embed(self.session_id, self.user_id, self.filter_contact, self.filter_type, 0)
            inv = db.get_inventory(self.user_id) if self.user_id else []
            return emb, inv

        embed, inv_items = await db.adb(_do_delete)
        view = PhoneMediaGalleryView(
            self.cog,
            self.session_id,
            self.user_id,
            self.filter_contact,
            self.filter_type,
            0,
            inv_items=inv_items,
        )
        await interaction.response.edit_message(embed=embed, view=view)

    async def _back_home(self, interaction: discord.Interaction):
        def _prep_home():
            emb = build_phone_home_embed(self.session_id, self.user_id)
            sess = db.get_session(self.session_id)
            return emb, sess

        embed, session = await db.adb(_prep_home)
        view = PhoneMainView(self.cog, self.session_id, self.user_id, session=session)
        await interaction.response.edit_message(embed=embed, view=view)



GossipFeedView = SocialFeedView


def _resolve_phone_ui_lang(user_id: int | None, session: dict | None = None) -> str:
    """Resolves the player's UI language code ('en', 'pl', 'ms', 'zh', 'de') for Discord Smartphone embeds."""
    try:
        if user_id:
            st = db.get_settings(int(user_id)) or {}
            if st.get("ui_language"):
                return str(st["ui_language"]).strip().lower()
            if st.get("language"):
                return str(st["language"]).strip().lower()
    except Exception:
        pass
    if isinstance(session, dict) and session.get("language"):
        return str(session["language"]).strip().lower()
    return "en"


def _build_realty_embed(
    payload: dict,
    selected_prop_id: str | None = None,
    notice: str = "",
    lang: str = "en",
) -> discord.Embed:
    """Builds the localized Smartphone Realty & Safehouse Registry embed for Discord."""
    from localization import get_realty_label

    rl = lambda k: get_realty_label(k, lang)
    gold = int(payload.get("gold") or 0)
    bonus = int(payload.get("property_slot_bonus") or 0)
    max_slots = int(payload.get("max_inventory_slots") or 30)
    starter = payload.get("starter_quarters")
    owned = payload.get("owned_properties") or []
    catalog = payload.get("catalog") or []

    desc_lines = [
        f"🪙 **{gold}g** | 🎒 **`+{bonus}`** (`{max_slots}`)"
    ]
    if notice:
        desc_lines.append(f"\n✨ *{notice}*")

    embed = discord.Embed(
        title=f"🏠 {rl('app_name')} — {rl('app_sub')}",
        description="\n".join(desc_lines),
        color=discord.Color.teal(),
    )

    res_lines = []
    if starter:
        prim_tag = f" `★ {rl('primary_home')}`" if starter.get("is_primary") else ""
        res_lines.append(
            f"• 🏢 **{starter['name']}** (`{rl('badge_starter')}`){prim_tag}\n"
            f"  ↳ 📍 {starter.get('zone_name', '')} — *{starter.get('room_name', 'Private Unit')}*"
        )
    for op in owned:
        prim_tag = f" `★ {rl('primary_home')}`" if op.get("is_primary") else ""
        keys = [h["name"] for h in (op.get("spare_key_holders") or [])]
        key_str = f" | 🔑 {', '.join(keys)}" if keys else ""
        res_lines.append(
            f"• 🏠 **{op['name']}** (`T{op['tier']}`){prim_tag}{key_str}\n"
            f"  ↳ 📍 {op.get('zone_name', '')} — `+{op.get('base_slots', 0)}`"
        )
    if res_lines:
        embed.add_field(name=f"🔑 {rl('tab_owned')}", value="\n".join(res_lines)[:1024], inline=False)

    sel_item = None
    if selected_prop_id:
        if starter and starter.get("property_id") == selected_prop_id:
            sel_item = {**starter, "is_owned": True, "is_starter": True}
        else:
            sel_item = next((c for c in catalog if c["property_id"] == selected_prop_id), None)

    if sel_item:
        perks = []
        if sel_item.get("base_slots"):
            perks.append(f"+{sel_item['base_slots']} Slots")
        if float(sel_item.get("rest_multiplier") or 1.0) > 1.0:
            perks.append(f"{sel_item['rest_multiplier']}x Rest")
        if int(sel_item.get("cha_invite_dc_mod") or 0) < 0:
            perks.append(f"{sel_item['cha_invite_dc_mod']} Invite DC")
        if int(sel_item.get("hangout_affinity_bonus") or 0) > 0:
            perks.append(f"+{sel_item['hangout_affinity_bonus']} Affinity")
        perk_line = " • ".join(perks) if perks else rl("starter_spare_key_note")
        status_txt = (
            rl("badge_starter")
            if sel_item.get("is_starter")
            else (rl("deed_owned") if sel_item.get("is_owned") else f"{rl('badge_for_sale')} — {sel_item.get('price', 0)}g")
        )
        embed.add_field(
            name=f"📋 {sel_item['name']} ({status_txt})",
            value=(
                f"📍 {sel_item.get('zone_name', '')}\n"
                f"✨ `{perk_line}`\n"
                f"*{sel_item.get('description', '')}*"
            )[:1024],
            inline=False,
        )
    else:
        mkt_lines = []
        for c in catalog[:9]:
            tag = f"✅ {rl('deed_owned')}" if c.get("is_owned") else f"🏷️ {c['price']}g"
            mkt_lines.append(f"• **T{c['tier']} {c['name']}** ({c.get('zone_name', '')}) — `{tag}`")
        if mkt_lines:
            embed.add_field(name=f"🏷️ {rl('tab_market')}", value="\n".join(mkt_lines)[:1024], inline=False)

    return embed


class PhoneRealtyView(PhoneOwnerRestrictedView):
    """Interactive Discord Smartphone Realty & Safehouse management view."""
    def __init__(
        self,
        cog,
        session_id: int,
        user_id: int,
        payload: dict,
        selected_prop_id: str | None = None,
        lang: str = "en",
    ):
        from localization import get_realty_label

        super().__init__(timeout=300)
        self.cog = cog
        self.session_id = session_id
        self.user_id = user_id
        self.payload = payload
        self.lang = lang or "en"
        rl = lambda k: get_realty_label(k, self.lang)
        starter = payload.get("starter_quarters")
        catalog = payload.get("catalog") or []

        if not selected_prop_id:
            prim_owned = next((c["property_id"] for c in catalog if c.get("is_primary")), None)
            selected_prop_id = prim_owned or (starter.get("property_id") if starter else (catalog[0]["property_id"] if catalog else None))
        self.selected_prop_id = selected_prop_id

        options: list[discord.SelectOption] = []
        if starter:
            s_pid = starter["property_id"]
            options.append(
                discord.SelectOption(
                    label=f"{starter['name']}"[:100],
                    value=s_pid,
                    description=f"{rl('badge_starter')} • {starter.get('zone_name', '')}"[:100],
                    emoji="🏢",
                    default=(s_pid == self.selected_prop_id),
                )
            )
        for c in catalog[:24]:
            cid = c["property_id"]
            status_lbl = f"★ {rl('primary_home')}" if c.get("is_primary") else (rl("deed_owned") if c.get("is_owned") else f"{c['price']}g")
            options.append(
                discord.SelectOption(
                    label=f"[T{c['tier']}] {c['name']}"[:100],
                    value=cid,
                    description=f"{status_lbl} • {c.get('zone_name', '')} (+{c.get('base_slots', 0)})"[:100],
                    emoji="🏠" if c.get("is_owned") else "🏷️",
                    default=(cid == self.selected_prop_id),
                )
            )

        if options:
            sel = discord.ui.Select(
                placeholder=f"🏠 {rl('tab_owned')} / {rl('tab_market')}..."[:100],
                min_values=1,
                max_values=1,
                options=options,
                row=0,
            )
            sel.callback = self._on_select_property
            self.add_item(sel)

        is_starter_sel = bool(starter and starter.get("property_id") == self.selected_prop_id)
        cat_sel = next((c for c in catalog if c["property_id"] == self.selected_prop_id), None)
        is_owned_deed = bool(cat_sel and cat_sel.get("is_owned"))
        is_primary_sel = bool(
            (is_starter_sel and starter.get("is_primary"))
            or (cat_sel and cat_sel.get("is_primary"))
        )

        buy_price = int(cat_sel.get("price") or 0) if cat_sel else 0
        buy_btn = discord.ui.Button(
            label=(f"{rl('buy_deed')} ({buy_price}g)" if (cat_sel and not is_owned_deed) else rl("deed_owned"))[:80],
            emoji="🪙",
            style=discord.ButtonStyle.success,
            disabled=bool(is_starter_sel or not cat_sel or is_owned_deed or not cat_sel.get("can_afford")),
            row=1,
        )
        prim_btn = discord.ui.Button(
            label=(rl("primary_home") if is_primary_sel else rl("set_primary"))[:80],
            emoji="⭐",
            style=discord.ButtonStyle.primary,
            disabled=bool(is_primary_sel or (not is_starter_sel and not is_owned_deed)),
            row=1,
        )
        key_btn = discord.ui.Button(
            label=rl("spare_keys_label")[:80],
            emoji="🔑",
            style=discord.ButtonStyle.secondary,
            disabled=not is_owned_deed,
            row=1,
        )
        home_btn = discord.ui.Button(
            label="Phone Home",
            emoji="📱",
            style=discord.ButtonStyle.secondary,
            row=1,
        )

        buy_btn.callback = self._buy_deed
        prim_btn.callback = self._set_primary
        key_btn.callback = self._open_spare_keys
        home_btn.callback = self._back_home

        self.add_item(buy_btn)
        self.add_item(prim_btn)
        self.add_item(key_btn)
        self.add_item(home_btn)

    async def _on_select_property(self, interaction: discord.Interaction):
        chosen = interaction.data["values"][0]
        from mechanics.world.locations.residences import build_realty_payload
        payload = await db.adb(build_realty_payload, self.session_id, self.user_id)
        embed = _build_realty_embed(payload, selected_prop_id=chosen, lang=self.lang)
        view = PhoneRealtyView(self.cog, self.session_id, self.user_id, payload, selected_prop_id=chosen, lang=self.lang)
        await interaction.response.edit_message(embed=embed, view=view)

    async def _buy_deed(self, interaction: discord.Interaction):
        from localization import get_realty_label
        from mechanics.system.concurrency import LockAcquisitionError, distributed_adventure_lock
        from mechanics.world.locations.residences import build_realty_payload

        if not self.selected_prop_id:
            return
        await interaction.response.defer()
        try:
            async with distributed_adventure_lock(self.user_id, self.session_id, raise_http_error=False):
                sess = await db.adb(db.get_session, self.session_id)
                if not sess or str(sess.get("status") or "active").strip().lower() != "active":
                    await interaction.followup.send("❌ This adventure session is no longer active.", ephemeral=True)
                    return
                res = await db.adb(db.atomic_purchase_property, self.session_id, self.user_id, self.selected_prop_id)
                payload = await db.adb(build_realty_payload, self.session_id, self.user_id)
        except LockAcquisitionError as lock_err:
            await interaction.followup.send(f"⏳ {lock_err}", ephemeral=True)
            return

        if not res.get("ok"):
            await interaction.followup.send(
                f"❌ {get_realty_label('purchase_failed', self.lang)} (`{res.get('reason', 'error')}`)",
                ephemeral=True,
            )
            return
        prop_nm = (res.get("catalog_entry") or {}).get("name") or self.selected_prop_id
        notice = f"{get_realty_label('purchased_ok', self.lang)} ({prop_nm})"
        embed = _build_realty_embed(payload, selected_prop_id=self.selected_prop_id, notice=notice, lang=self.lang)
        view = PhoneRealtyView(self.cog, self.session_id, self.user_id, payload, selected_prop_id=self.selected_prop_id, lang=self.lang)
        await interaction.edit_original_response(embed=embed, view=view)

    async def _set_primary(self, interaction: discord.Interaction):
        from localization import get_realty_label
        from mechanics.system.concurrency import LockAcquisitionError, distributed_session_lock
        from mechanics.world.locations.residences import build_realty_payload

        if not self.selected_prop_id:
            return
        await interaction.response.defer()
        try:
            async with distributed_session_lock(self.session_id, raise_http_error=False):
                sess = await db.adb(db.get_session, self.session_id)
                if not sess or str(sess.get("status") or "active").strip().lower() != "active":
                    await interaction.followup.send("❌ This adventure session is no longer active.", ephemeral=True)
                    return
                res = await db.adb(db.set_primary_property, self.session_id, self.selected_prop_id)
                payload = await db.adb(build_realty_payload, self.session_id, self.user_id)
        except LockAcquisitionError as lock_err:
            await interaction.followup.send(f"⏳ {lock_err}", ephemeral=True)
            return

        if not res.get("ok"):
            await interaction.followup.send("❌ Could not update Primary Home.", ephemeral=True)
            return
        embed = _build_realty_embed(
            payload,
            selected_prop_id=self.selected_prop_id,
            notice=get_realty_label("primary_updated", self.lang),
            lang=self.lang,
        )
        view = PhoneRealtyView(self.cog, self.session_id, self.user_id, payload, selected_prop_id=self.selected_prop_id, lang=self.lang)
        await interaction.edit_original_response(embed=embed, view=view)

    async def _open_spare_keys(self, interaction: discord.Interaction):
        from localization import get_realty_label
        from mechanics.world.locations.residences import build_realty_payload
        payload = await db.adb(build_realty_payload, self.session_id, self.user_id)
        owned_entry = next(
            (o for o in (payload.get("owned_properties") or []) if o["property_id"] == self.selected_prop_id),
            None,
        )
        if not owned_entry:
            await interaction.response.send_message(f"🔑 {get_realty_label('starter_spare_key_note', self.lang)}", ephemeral=True)
            return
        eligible = payload.get("eligible_spare_key_contacts") or []
        holders = owned_entry.get("spare_key_holders") or []
        if not eligible and not holders:
            await interaction.response.send_message(
                f"🔑 {get_realty_label('no_eligible_contacts', self.lang)}",
                ephemeral=True,
            )
            return
        view = PhoneSpareKeySelectView(self.cog, self.session_id, self.user_id, payload, owned_entry, lang=self.lang)
        embed = _build_realty_embed(
            payload,
            selected_prop_id=self.selected_prop_id,
            notice=get_realty_label("spare_keys_label", self.lang),
            lang=self.lang,
        )
        await interaction.response.edit_message(embed=embed, view=view)

    async def _back_home(self, interaction: discord.Interaction):
        def _prep_home():
            emb = build_phone_home_embed(self.session_id, self.user_id)
            sess = db.get_session(self.session_id)
            return emb, sess

        embed, session = await db.adb(_prep_home)
        view = PhoneMainView(self.cog, self.session_id, self.user_id, session=session)
        await interaction.response.edit_message(embed=embed, view=view)


class PhoneSpareKeySelectView(PhoneOwnerRestrictedView):
    """Sub-view to grant or revoke Spare Keys on an owned property deed."""
    def __init__(self, cog, session_id: int, user_id: int, payload: dict, owned_entry: dict, lang: str = "en"):
        from localization import get_realty_label

        super().__init__(timeout=300)
        self.cog = cog
        self.session_id = session_id
        self.user_id = user_id
        self.payload = payload
        self.lang = lang or "en"
        self.property_id = owned_entry["property_id"]
        rl = lambda k: get_realty_label(k, self.lang)

        holders = {str(h["npc_id"]).lower(): h for h in (owned_entry.get("spare_key_holders") or [])}
        options: list[discord.SelectOption] = []
        seen: set[str] = set()

        for h_low, h in holders.items():
            seen.add(h_low)
            options.append(
                discord.SelectOption(
                    label=f"{rl('revoke_key')}: {h['name']}"[:100],
                    value=f"revoke:{h['npc_id']}"[:100],
                    description=rl("revoke_key")[:100],
                    emoji="🚫",
                )
            )
        for c in (payload.get("eligible_spare_key_contacts") or [])[:20]:
            cid_low = str(c["npc_id"]).lower()
            if cid_low in seen:
                continue
            seen.add(cid_low)
            rel_lbl = "♥" if c.get("is_romantic") else f"+{c.get('relationship_score', 0)}"
            options.append(
                discord.SelectOption(
                    label=f"{rl('give_spare_key')}: {c['name']}"[:100],
                    value=f"grant:{c['npc_id']}"[:100],
                    description=rel_lbl[:100],
                    emoji="🔑",
                )
            )

        if options:
            sel = discord.ui.Select(
                placeholder=f"🔑 {rl('spare_keys_label')}..."[:100],
                min_values=1,
                max_values=1,
                options=options[:25],
                row=0,
            )
            sel.callback = self._on_toggle_key
            self.add_item(sel)

        back_btn = discord.ui.Button(label=rl("app_name")[:80], emoji="🔙", style=discord.ButtonStyle.secondary, row=1)
        back_btn.callback = self._back_to_realty
        self.add_item(back_btn)

    async def _on_toggle_key(self, interaction: discord.Interaction):
        from localization import get_realty_label
        from mechanics.system.concurrency import LockAcquisitionError, distributed_session_lock
        from mechanics.world.locations.residences import build_realty_payload

        raw_val = interaction.data["values"][0]
        mode, npc_id = raw_val.split(":", 1)
        await interaction.response.defer()
        try:
            async with distributed_session_lock(self.session_id, raise_http_error=False):
                sess = await db.adb(db.get_session, self.session_id)
                if not sess or str(sess.get("status") or "active").strip().lower() != "active":
                    await interaction.followup.send("❌ This adventure session is no longer active.", ephemeral=True)
                    return
                if mode == "revoke":
                    res = await db.adb(db.revoke_property_spare_key, self.session_id, self.property_id, npc_id)
                    msg = get_realty_label("key_revoked", self.lang)
                else:
                    res = await db.adb(db.grant_property_spare_key, self.session_id, self.property_id, npc_id)
                    msg = f"{get_realty_label('key_granted', self.lang)} ({res.get('npc_name') or npc_id})"
                payload = await db.adb(build_realty_payload, self.session_id, self.user_id)
        except LockAcquisitionError as lock_err:
            await interaction.followup.send(f"⏳ {lock_err}", ephemeral=True)
            return

        if not res.get("ok"):
            await interaction.followup.send(f"❌ `{res.get('reason', 'error')}`", ephemeral=True)
            return
        embed = _build_realty_embed(payload, selected_prop_id=self.property_id, notice=msg, lang=self.lang)
        view = PhoneRealtyView(self.cog, self.session_id, self.user_id, payload, selected_prop_id=self.property_id, lang=self.lang)
        await interaction.edit_original_response(embed=embed, view=view)

    async def _back_to_realty(self, interaction: discord.Interaction):
        from mechanics.world.locations.residences import build_realty_payload
        payload = await db.adb(build_realty_payload, self.session_id, self.user_id)
        embed = _build_realty_embed(payload, selected_prop_id=self.property_id, lang=self.lang)
        view = PhoneRealtyView(self.cog, self.session_id, self.user_id, payload, selected_prop_id=self.property_id, lang=self.lang)
        await interaction.response.edit_message(embed=embed, view=view)


RealtyView = PhoneRealtyView
