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

from .embeds import *
from .embeds import _build_media_item_detail_embed, _build_dm_chat_embed, _build_gossip_feed_embed, _build_social_profile_embed
from .messaging import *

class PhoneMainView(discord.ui.View):
    """The Home Screen of the Smartphone / Cyberdeck Hub."""
    def __init__(self, cog, session_id: int, user_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.session_id = session_id
        self.user_id = user_id

        session = db.get_session(session_id)
        scen_key = session.get("scenario", "fantasy") if session else "fantasy"
        branding = get_phone_branding(scen_key)

        contacts_app = branding.get("contacts_app_name", "Contacts")
        gallery_app = branding.get("gallery_app_name", "Photo Vault")
        gallery_emoji = branding.get("gallery_emoji", "📸")

        contacts_btn = discord.ui.Button(label=contacts_app, emoji="👥", style=discord.ButtonStyle.primary, row=0)
        dm_btn = discord.ui.Button(label=branding["dm_app_name"], emoji="💬", style=discord.ButtonStyle.primary, row=0)
        feed_btn = discord.ui.Button(label=branding["feed_app_name"], emoji=branding["feed_emoji"], style=discord.ButtonStyle.secondary, row=0)
        gallery_btn = discord.ui.Button(label=gallery_app, emoji=gallery_emoji, style=discord.ButtonStyle.secondary, row=0)

        bounty_btn = discord.ui.Button(label=branding["bounty_app_name"], emoji="📋", style=discord.ButtonStyle.secondary, row=1)
        shop_btn = discord.ui.Button(label=branding["shop_app_name"], emoji="🛍️", style=discord.ButtonStyle.secondary, row=1)
        close_btn = discord.ui.Button(label="Lock Screen", emoji="🔒", style=discord.ButtonStyle.secondary, row=1)

        contacts_btn.callback = self._open_contacts
        dm_btn.callback = self._open_dms
        feed_btn.callback = self._open_feed
        gallery_btn.callback = self._open_gallery
        bounty_btn.callback = self._open_bounties
        shop_btn.callback = self._open_shop
        close_btn.callback = self._close_phone

        self.add_item(contacts_btn)
        self.add_item(dm_btn)
        self.add_item(feed_btn)
        self.add_item(gallery_btn)
        self.add_item(bounty_btn)
        self.add_item(shop_btn)
        self.add_item(close_btn)

    async def _open_gallery(self, interaction: discord.Interaction):
        embed = build_media_gallery_embed(self.session_id, self.user_id, filter_contact=None, filter_type=None, page=0)
        view = PhoneMediaGalleryView(self.cog, self.session_id, self.user_id, filter_contact=None, filter_type=None, page=0)
        await interaction.response.edit_message(embed=embed, view=view)

    async def _open_contacts(self, interaction: discord.Interaction):
        char = db.get_character(self.user_id)
        contacts = db.get_contacts(self.session_id, character_id=char.get("id", 0)) if char else []
        session = db.get_session(self.session_id)
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
        char = db.get_character(self.user_id)
        contacts = db.get_contacts(self.session_id, character_id=char.get("id", 0)) if char else []
        session = db.get_session(self.session_id)
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
        session = db.get_session(self.session_id)
        scen_key = session.get("scenario", "fantasy") if session else "fantasy"
        branding = get_phone_branding(scen_key)

        posts = await generate_gossip_feed_posts(session)
        state_summary = get_social_state_summary(self.session_id, session)
        embed = _build_gossip_feed_embed(session, posts, branding, charges=state_summary["charges"])
        view = SocialFeedView(self.cog, self.session_id, self.user_id, posts)
        await interaction.followup.edit_message(message_id=interaction.message.id, embed=embed, view=view)

    async def _open_bounties(self, interaction: discord.Interaction):
        from game_engine import generate_bounty_board
        from cogs.adventure import _build_bounty_board_embed, BountyBoardView
        await interaction.response.defer()
        session = db.get_session(self.session_id)
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

class DMContactSelectView(discord.ui.View):
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

        embed = _build_dm_chat_embed(self.session_id, contact)
        view = DMChatView(self.cog, self.session_id, self.user_id, contact, list(self.contacts_dict.values()))
        await interaction.response.edit_message(embed=embed, view=view)

    async def _back_to_home(self, interaction: discord.Interaction):
        embed = build_phone_home_embed(self.session_id, self.user_id)
        view = PhoneMainView(self.cog, self.session_id, self.user_id)
        await interaction.response.edit_message(embed=embed, view=view)

class DMChatView(discord.ui.View):
    """Active chat view with a specific contact."""
    def __init__(self, cog, session_id: int, user_id: int, contact: dict, all_contacts: list[dict]):
        super().__init__(timeout=300)
        self.cog = cog
        self.session_id = session_id
        self.user_id = user_id
        self.contact = contact
        self.all_contacts = all_contacts

        session = db.get_session(session_id)
        scen_key = session.get("scenario", "fantasy") if session else "fantasy"
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
        char = db.get_character(self.user_id)
        session = db.get_session(self.session_id)
        loc = session.get("current_location", "around here") if session else "around here"
        caption = generate_player_photo_caption(char, intent="photo", location=loc)
        msg = f"Sending you a quick snapshot from {loc}! 📸\n[Attached Photo: {caption}]\nWhat are you up to right now?"
        await self._send_dm_action(interaction, msg, intent="photo")

    async def _quick_nsfw_photo(self, interaction: discord.Interaction):
        char = db.get_character(self.user_id)
        caption = generate_player_photo_caption(char, intent="nsfw_photo")
        msg = f"Sending an intimate selfie just for your eyes... 🔞\n[Attached Intimate Photo: {caption}]\nHope you like what you see 😉"
        await self._send_dm_action(interaction, msg, intent="nsfw_photo")

    async def _quick_intel_rumor(self, interaction: discord.Interaction):
        npc_id = self.contact.get("npc_id") or self.contact["name"].lower().replace(" ", "_")
        history_rows = db.get_phone_messages(self.session_id, npc_id, limit=2)
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
        char = db.get_character(self.user_id)
        session = db.get_session(self.session_id)

        if not message_text:
            message_text = await generate_player_chat_message(session, self.contact, char, intent=intent)

        reply_data = await generate_contact_dm_reply(session, self.contact, char, message_text, intent=intent)

        # Refresh contact data with new score
        npc_id = self.contact.get("npc_id") or self.contact["name"].lower().replace(" ", "_")
        updated_contact = db.get_contact(self.session_id, npc_id, character_id=char.get("id", 0)) or self.contact
        self.contact = updated_contact

        embed = _build_dm_chat_embed(self.session_id, updated_contact, last_reply=reply_data)
        await interaction.followup.edit_message(message_id=interaction.message.id, embed=embed, view=self)

    async def _back_to_contacts(self, interaction: discord.Interaction):
        session = db.get_session(self.session_id)
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

class SocialFeedView(discord.ui.View):
    """View displaying social timeline posts with single rumor scouring and character discovery buttons."""
    def __init__(self, cog, session_id: int, user_id: int, posts: list[dict]):
        super().__init__(timeout=300)
        self.cog = cog
        self.session_id = session_id
        self.user_id = user_id
        self.posts = posts

        session = db.get_session(session_id)
        state_summary = get_social_state_summary(session_id, session)
        charges = state_summary["charges"]

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
        back_btn = discord.ui.Button(label="Phone Home", emoji="📱", style=discord.ButtonStyle.secondary, row=1)

        refresh_btn.callback = self._refresh_feed
        back_btn.callback = self._back_to_home

        self.add_item(refresh_btn)
        self.add_item(back_btn)

    async def _dig_rumors(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        session = db.get_session(self.session_id)
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
        session = db.get_session(self.session_id)
        scen_key = session.get("scenario", "fantasy") if session else "fantasy"
        branding = get_phone_branding(scen_key)

        profile = discover_suggested_peer(self.session_id, self.user_id)
        if not profile:
            await interaction.followup.send("⚠️ No student profiles available right now.", ephemeral=True)
            return

        embed = _build_social_profile_embed(self.session_id, profile, branding)
        view = SocialProfileView(self.cog, self.session_id, self.user_id, profile, self.posts)
        await interaction.followup.edit_message(message_id=interaction.message.id, embed=embed, view=view)

    async def _refresh_feed(self, interaction: discord.Interaction):
        await interaction.response.defer()
        session = db.get_session(self.session_id)
        scen_key = session.get("scenario", "fantasy") if session else "fantasy"
        branding = get_phone_branding(scen_key)

        new_posts = await generate_gossip_feed_posts(session, force_refresh=True)
        state_summary = get_social_state_summary(self.session_id, session)
        embed = _build_gossip_feed_embed(session, new_posts, branding, charges=state_summary["charges"])
        view = SocialFeedView(self.cog, self.session_id, self.user_id, new_posts)
        await interaction.followup.edit_message(message_id=interaction.message.id, embed=embed, view=view)

    async def _back_to_home(self, interaction: discord.Interaction):
        embed = build_phone_home_embed(self.session_id, self.user_id)
        view = PhoneMainView(self.cog, self.session_id, self.user_id)
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
        profile = lookup_social_profile(self.session_id, self.user_id, query)
        session = db.get_session(self.session_id)
        scen_key = session.get("scenario", "fantasy") if session else "fantasy"
        branding = get_phone_branding(scen_key)

        if not profile:
            await interaction.followup.send(
                f"🔎 **No user found:** No matching profile found for **'{query}'** in the network directory.",
                ephemeral=True
            )
            return

        embed = _build_social_profile_embed(self.session_id, profile, branding)
        view = SocialProfileView(self.cog, self.session_id, self.user_id, profile, self.feed_view.posts)
        await interaction.followup.edit_message(message_id=interaction.message.id, embed=embed, view=view)

class SocialProfileView(discord.ui.View):
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
            if cooldown > 0:
                req_btn = discord.ui.Button(
                    label=f"Request Pending ({cooldown}t CD)",
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
        session = db.get_session(self.session_id)
        res = resolve_social_friend_request(session, self.user_id, self.profile)

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

        scen_key = session.get("scenario", "fantasy") if session else "fantasy"
        branding = get_phone_branding(scen_key)

        if res.get("on_cooldown"):
            await interaction.response.send_message(res["message"], ephemeral=True)
            return

        mod_text = " • ".join(res.get("mod_reasons", [])) or "None"
        msg = (
            f"🎲 **{stat_name} Social Check ({chance}%)**: {tier_emoji} **{tier_label}**\n"
            f"⚡ **Modifiers:** `{mod_text}`\n\n"
            f"{res['message']}"
        )

        updated_profile = lookup_social_profile(self.session_id, self.user_id, self.profile["name"]) or self.profile
        embed = _build_social_profile_embed(self.session_id, updated_profile, branding)
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
        char = db.get_character(self.user_id)
        contacts = db.get_contacts(self.session_id, character_id=char.get("id", 0)) if char else []
        contact = db.get_contact(self.session_id, self.profile["npc_id"], character_id=char.get("id", 0)) if char else None

        if not contact:
            await interaction.response.send_message("Contact not found.", ephemeral=True)
            return

        embed = _build_dm_chat_embed(self.session_id, contact)
        view = DMChatView(self.cog, self.session_id, self.user_id, contact, contacts)
        await interaction.response.edit_message(embed=embed, view=view)

    async def _back_to_feed(self, interaction: discord.Interaction):
        session = db.get_session(self.session_id)
        scen_key = session.get("scenario", "fantasy") if session else "fantasy"
        branding = get_phone_branding(scen_key)
        state_summary = get_social_state_summary(self.session_id, session)
        embed = _build_gossip_feed_embed(session, self.posts, branding, charges=state_summary["charges"])
        view = SocialFeedView(self.cog, self.session_id, self.user_id, self.posts)
        await interaction.response.edit_message(embed=embed, view=view)

class PhoneMediaGalleryView(discord.ui.View):
    """Interactive media album browser with contact filtering, category tags, and pagination."""
    def __init__(self, cog, session_id: int, user_id: int, filter_contact: str = None, filter_type: str = None, page: int = 0):
        super().__init__(timeout=300)
        self.cog = cog
        self.session_id = session_id
        self.user_id = user_id
        self.filter_contact = filter_contact
        self.filter_type = filter_type
        self.page = page

        inv_items = db.get_inventory(user_id) if user_id else []
        from mechanics.combat.items import is_digital_item, parse_digital_item_metadata
        all_digital = [it for it in inv_items if is_digital_item(it)]

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

    async def _on_select_item(self, interaction: discord.Interaction):
        item_id = interaction.data["values"][0]
        item = self.items_dict.get(item_id)
        if not item:
            inv = db.get_inventory(self.user_id) if self.user_id else []
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
        embed = build_media_gallery_embed(self.session_id, self.user_id, filter_contact=new_fc, filter_type=self.filter_type, page=0)
        view = PhoneMediaGalleryView(self.cog, self.session_id, self.user_id, filter_contact=new_fc, filter_type=self.filter_type, page=0)
        await interaction.response.edit_message(embed=embed, view=view)

    async def _filter_all(self, interaction: discord.Interaction):
        embed = build_media_gallery_embed(self.session_id, self.user_id, filter_contact=self.filter_contact, filter_type=None, page=0)
        view = PhoneMediaGalleryView(self.cog, self.session_id, self.user_id, filter_contact=self.filter_contact, filter_type=None, page=0)
        await interaction.response.edit_message(embed=embed, view=view)

    async def _filter_photos(self, interaction: discord.Interaction):
        embed = build_media_gallery_embed(self.session_id, self.user_id, filter_contact=self.filter_contact, filter_type="photos", page=0)
        view = PhoneMediaGalleryView(self.cog, self.session_id, self.user_id, filter_contact=self.filter_contact, filter_type="photos", page=0)
        await interaction.response.edit_message(embed=embed, view=view)

    async def _filter_intimate(self, interaction: discord.Interaction):
        embed = build_media_gallery_embed(self.session_id, self.user_id, filter_contact=self.filter_contact, filter_type="intimate", page=0)
        view = PhoneMediaGalleryView(self.cog, self.session_id, self.user_id, filter_contact=self.filter_contact, filter_type="intimate", page=0)
        await interaction.response.edit_message(embed=embed, view=view)

    async def _filter_videos(self, interaction: discord.Interaction):
        embed = build_media_gallery_embed(self.session_id, self.user_id, filter_contact=self.filter_contact, filter_type="videos", page=0)
        view = PhoneMediaGalleryView(self.cog, self.session_id, self.user_id, filter_contact=self.filter_contact, filter_type="videos", page=0)
        await interaction.response.edit_message(embed=embed, view=view)

    async def _prev_page(self, interaction: discord.Interaction):
        p = max(0, self.page - 1)
        embed = build_media_gallery_embed(self.session_id, self.user_id, filter_contact=self.filter_contact, filter_type=self.filter_type, page=p)
        view = PhoneMediaGalleryView(self.cog, self.session_id, self.user_id, filter_contact=self.filter_contact, filter_type=self.filter_type, page=p)
        await interaction.response.edit_message(embed=embed, view=view)

    async def _next_page(self, interaction: discord.Interaction):
        p = self.page + 1
        embed = build_media_gallery_embed(self.session_id, self.user_id, filter_contact=self.filter_contact, filter_type=self.filter_type, page=p)
        view = PhoneMediaGalleryView(self.cog, self.session_id, self.user_id, filter_contact=self.filter_contact, filter_type=self.filter_type, page=p)
        await interaction.response.edit_message(embed=embed, view=view)

    async def _back_home(self, interaction: discord.Interaction):
        embed = build_phone_home_embed(self.session_id, self.user_id)
        view = PhoneMainView(self.cog, self.session_id, self.user_id)
        await interaction.response.edit_message(embed=embed, view=view)

class PhoneMediaDetailView(discord.ui.View):
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
        embed = build_media_gallery_embed(self.session_id, self.user_id, self.filter_contact, self.filter_type, self.page)
        view = PhoneMediaGalleryView(self.cog, self.session_id, self.user_id, self.filter_contact, self.filter_type, self.page)
        await interaction.response.edit_message(embed=embed, view=view)

    async def _delete_item(self, interaction: discord.Interaction):
        item_id = self.item.get("id")
        if item_id:
            db.remove_item(self.user_id, int(item_id))
        embed = build_media_gallery_embed(self.session_id, self.user_id, self.filter_contact, self.filter_type, 0)
        view = PhoneMediaGalleryView(self.cog, self.session_id, self.user_id, self.filter_contact, self.filter_type, 0)
        await interaction.response.edit_message(embed=embed, view=view)

    async def _back_home(self, interaction: discord.Interaction):
        embed = build_phone_home_embed(self.session_id, self.user_id)
        view = PhoneMainView(self.cog, self.session_id, self.user_id)
        await interaction.response.edit_message(embed=embed, view=view)



GossipFeedView = SocialFeedView
