from .constants import *
import asyncio
import json
import logging
import random
import re
import time
import discord
from discord import app_commands
from discord.ext import commands
import db
from db import adb
import game_engine
import image_client
from character_data import (
    XP_REWARDS, STATS, STAT_NAMES, STAT_EMOJI, MAX_LEVEL, MAX_STAT_VALUE,
    get_item_icon, format_item_with_icon, get_class_templates, get_starting_weapons,
    get_starter_gear_by_class, get_starting_items, inventory_capacity
)
from cogs.character import build_character_sheet_embed
from db import STAT_COLUMN
from scenario_data import DEFAULT_SCENARIO, ScenarioError, load_scenarios, resolve_scenario_key
from skill_check import resolve_check, success_chance, CheckResult
from mechanics.combat.merchant import (
    apply_merchant_encounter_result as _apply_merchant_encounter_result,
    handle_talk_to_merchant as _handle_talk_to_merchant,
    build_merchant_embed as _merchant_embed,
    discounted_price as _discounted_price,
    sell_bonus_price as _sell_bonus_price,
    MerchantView,
    MerchantVoteView,
    BuySelectView,
    SellSelectView,
    RumorView,
)
from mechanics.social.races import normalize_race
from mechanics.social.persona import normalize_appearance
from mechanics.world.locations import is_location_engine_enabled, get_discovered_location_tree, is_hub_location
from mechanics.narrative.bounty import QUEST_TYPE_ICONS, get_quest_type_icon as _quest_type_icon
from mechanics.combat.items import parse_item_effect, apply_item_to_target
import unicodedata
from ..embeds import *
from ..embeds import _build_bounties_embed, _build_bounty_board_embed, _build_campaign_goals_embed, _build_caseboard_embed, _build_history_embed, _build_main_quest_embed, _build_quest_log_embed, _choice_button_label, _format_items_gained, _format_items_gained_multi, _format_tracker_entity, _get_choice_emoji, _get_choice_quest_icon, _get_choice_skill_emoji, _get_quest_scenario_labels, _is_dialogue_partner, _location_text, _norm_name, _parse_status_effects, _party_vitals_text, _safe_add_field, _safe_int, _scenario_command_choices, _strip_leading_emojis, _tracker_group_text, _tracker_header, _truncate_embed_text, _truncate_field_name, _truncate_field_value
from ..embeds import _RESULT_COLORS, _RESULT_TITLES, _scenario_command_choices, _parse_status_effects, _party_vitals_text, _location_text, _safe_int, _truncate_field_value, _truncate_field_name, _safe_add_field, _norm_name, _is_dialogue_partner, _format_tracker_entity, _tracker_group_text, _strip_leading_emojis, _get_choice_quest_icon, _get_choice_skill_emoji, _get_choice_emoji, _format_items_gained, _format_items_gained_multi, _tracker_header, _truncate_embed_text, _choice_button_label, _get_quest_scenario_labels, _build_campaign_goals_embed, _build_main_quest_embed, _build_bounties_embed, _build_history_embed, _build_caseboard_embed, _build_quest_log_embed, _build_bounty_board_embed

class PartyDialogueSelectView(discord.ui.View):
    def __init__(self, cog: "AdventureCog", session_id: int, user_id: int, sync: bool = False):
        super().__init__(timeout=120)
        self.cog = cog
        self.session_id = session_id
        self.user_id = user_id
        self.sync = sync

        party_npcs = db.get_session_party_npcs(session_id)
        if party_npcs:
            self.add_item(PartyCompanionSelectDropdown(cog, session_id, user_id, party_npcs, sync=sync))

class PartyCompanionSelectDropdown(discord.ui.Select):
    def __init__(self, cog: "AdventureCog", session_id: int, user_id: int, party_npcs: list[dict], sync: bool = False):
        self.cog = cog
        self.session_id = session_id
        self.user_id = user_id
        self.sync = sync

        options = []
        for npc in party_npcs:
            name = npc.get("name", "Companion")
            role = npc.get("role", "Companion")
            lvl = npc.get("level", 1)
            hp = npc.get("hp", 20)
            max_hp = npc.get("max_hp", 20)
            desc = f"Lvl {lvl} {role} | HP: {hp}/{max_hp}"
            options.append(discord.SelectOption(label=name[:100], value=name, description=desc[:100], emoji="🤝"))

        super().__init__(placeholder="Select a companion to speak with...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        npc_name = self.values[0]
        embed = discord.Embed(
            title=f"🤝 Party Companion: {npc_name}",
            description=f"Choose an interaction with **{npc_name}**:",
            color=discord.Color.teal()
        )
        view = PartyCompanionActionView(self.cog, self.session_id, self.user_id, npc_name, sync=self.sync)
        await interaction.response.edit_message(embed=embed, view=view)

class PartyCompanionActionView(discord.ui.View):
    def __init__(self, cog: "AdventureCog", session_id: int, user_id: int, npc_name: str, sync: bool = False):
        super().__init__(timeout=120)
        self.cog = cog
        self.session_id = session_id
        self.user_id = user_id
        self.npc_name = npc_name
        self.sync = sync

    @discord.ui.button(label="Friendly Chat & Tactics", style=discord.ButtonStyle.primary, emoji="💬", row=0)
    async def chat_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done():
            try:
                await interaction.response.defer()
            except Exception:
                pass
        action_text = f"Have a friendly chat and discuss tactics with {self.npc_name}."
        if self.sync:
            await self.cog.handle_sync_pick(interaction, self.session_id, custom_text=action_text)
        else:
            await self.cog.handle_action(interaction, self.session_id, custom_text=action_text)

    @discord.ui.button(label="Ask About Backstory", style=discord.ButtonStyle.secondary, emoji="🔍", row=0)
    async def backstory_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done():
            try:
                await interaction.response.defer()
            except Exception:
                pass
        action_text = f"Inquire about {self.npc_name}'s personal background, history, and motivations."
        if self.sync:
            await self.cog.handle_sync_pick(interaction, self.session_id, custom_text=action_text)
        else:
            await self.cog.handle_action(interaction, self.session_id, custom_text=action_text)

    @discord.ui.button(label="Flirt / Close Moment", style=discord.ButtonStyle.secondary, emoji="❤️", row=0)
    async def flirt_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done():
            try:
                await interaction.response.defer()
            except Exception:
                pass
        action_text = f"Flirt with {self.npc_name} and share a close, intimate moment."
        if self.sync:
            await self.cog.handle_sync_pick(interaction, self.session_id, custom_text=action_text)
        else:
            await self.cog.handle_action(interaction, self.session_id, custom_text=action_text)

    @discord.ui.button(label="Dismiss from Party", style=discord.ButtonStyle.danger, emoji="🚪", row=1)
    async def dismiss_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        removed = db.remove_session_party_npc(self.session_id, self.npc_name)
        origin_loc = (removed.get("origin_location") if removed else "") or "Solaria ➔ The Boar's Tusk Tavern ➔ Hearthside Table"
        
        embed = discord.Embed(
            title="👋 Companion Dismissed",
            description=f"**{self.npc_name}** has departed your party and safely returned to **{origin_loc}**.\n\nYou can re-recruit them whenever you visit that settlement!",
            color=discord.Color.orange()
        )
        for item in self.children:
            item.disabled = True
        try:
            await interaction.response.edit_message(embed=embed, view=self)
        except Exception:
            pass
        
        if not self.sync:
            action_text = f"Part ways warmly with {self.npc_name} as they return home to {origin_loc}."
            await self.cog.handle_action(interaction, self.session_id, custom_text=action_text)

class JoinView(discord.ui.View):
    def __init__(self, cog: "AdventureCog", session_id: int):
        super().__init__(timeout=1800)
        self.cog = cog
        self.session_id = session_id

    @discord.ui.button(label="Join Game", style=discord.ButtonStyle.success, emoji="🙋")
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        char = db.get_character(interaction.user.id)
        if not char:
            await interaction.response.send_message(
                "You need a character first. Use `/character create`.", ephemeral=True)
            return
        if db.get_active_session_id_for_user(interaction.user.id):
            await interaction.response.send_message(
                "You're already in an active adventure.", ephemeral=True)
            return

        await interaction.response.defer()
        try:
            session = db.join_session(self.session_id, interaction.user.id)
        except ValueError as e:
            await interaction.followup.send(str(e), ephemeral=True)
            return

        if session["status"] != "active":
            await interaction.edit_original_response(
                content=f"**{char['name']}** joined! Still waiting for more players...", view=self)
            return

        for child in self.children:
            child.disabled = True
        await interaction.edit_original_response(
            content=f"**{char['name']}** joined! The party is ready — beginning the adventure below.",
            view=self)
        await self.cog.launch_opening_scene(interaction, session)

