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

class StatPointView(discord.ui.View):
    """Shown when a character has unspent stat points from leveling up.
    Works both as a standalone `/character levelup` response and as an
    auto-posted announcement after a turn resolves."""

    def __init__(self, user_id: int):
        super().__init__(timeout=600)
        self.user_id = user_id
        char = db.get_character(user_id)
        for stat in STATS:
            at_cap = bool(char) and char[STAT_COLUMN[stat]] >= MAX_STAT_VALUE
            button = discord.ui.Button(
                label=f"{STAT_NAMES[stat]} (MAX)" if at_cap else STAT_NAMES[stat],
                emoji=STAT_EMOJI[stat],
                style=discord.ButtonStyle.secondary, custom_id=f"lvl_{stat}",
                disabled=at_cap)
            button.callback = self._make_callback(stat)
            self.add_item(button)

    def _make_callback(self, stat: str):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.user_id:
                await interaction.response.send_message("These points aren't yours to spend.",
                                                          ephemeral=True)
                return
            result = await adb(db.spend_stat_point, self.user_id, stat)

            if result == "no_points":
                for child in self.children:
                    child.disabled = True
                await interaction.response.edit_message(
                    content="All stat points have been spent!", view=self)
                self.stop()
                return

            if result == "capped":
                await interaction.response.send_message(
                    f"**{STAT_NAMES[stat]}** is already at the maximum ({MAX_STAT_VALUE}) -- "
                    f"choose a different stat.", ephemeral=True)
                return

            char = await adb(db.get_character, self.user_id)
            remaining = char["pending_stat_points"]
            content = f"**{STAT_NAMES[stat]}** increased to {char[STAT_COLUMN[stat]]}! "

            # Re-disable any button(s) that just hit the cap, and stop
            # offering points once none remain unspent.
            all_capped = True
            for child in self.children:
                child_stat = child.custom_id.removeprefix("lvl_")
                if char[STAT_COLUMN[child_stat]] >= MAX_STAT_VALUE:
                    child.disabled = True
                    child.label = f"{STAT_NAMES[child_stat]} (MAX)"
                else:
                    all_capped = False

            if remaining > 0 and not all_capped:
                content += f"You have **{remaining}** point(s) left to spend:"
                await interaction.response.edit_message(content=content, view=self)
            else:
                if remaining > 0 and all_capped:
                    content += (f"You still have **{remaining}** point(s), but every stat is "
                                f"already at the maximum ({MAX_STAT_VALUE}) -- nowhere left to put them.")
                else:
                    content += "All points spent!"
                for child in self.children:
                    child.disabled = True
                await interaction.response.edit_message(content=content, view=self)
                self.stop()
        return callback

class LoadoutCustomClassModal(discord.ui.Modal, title="Describe Your Profession"):
    class_name = discord.ui.TextInput(
        label="Profession / Role Name", placeholder="e.g. Netrunner, Street Samurai, Exorcist", max_length=40
    )
    description = discord.ui.TextInput(
        label="Description & Playstyle", style=discord.TextStyle.paragraph,
        placeholder="What is their background, skillset, quirks, or fighting style?", max_length=300, required=False
    )

    def __init__(self, cog: "AdventureCog", user_id: int, session_config: dict):
        super().__init__()
        self.cog = cog
        self.user_id = user_id
        self.session_config = session_config

    async def on_submit(self, interaction: discord.Interaction):
        c_name = str(self.class_name).strip()
        c_desc = str(self.description).strip()
        view = LoadoutWeaponSelectView(self.cog, self.user_id, self.session_config, c_name, c_desc)
        await interaction.response.send_message(
            content=f"Chosen Profession: **{c_name}**\nNow choose your starting weapon:",
            view=view, ephemeral=True
        )

class LoadoutClassSelectView(discord.ui.View):
    def __init__(self, cog: "AdventureCog", user_id: int, session_config: dict):
        super().__init__(timeout=300)
        self.cog = cog
        self.user_id = user_id
        self.session_config = session_config
        scenario = session_config.get("scenario", "fantasy")

        templates = get_class_templates(scenario)
        options = []
        for cls_name, cls_data in list(templates.items())[:24]:
            desc = cls_data.get("description", "")[:100]
            options.append(discord.SelectOption(label=cls_name, description=desc))

        options.append(discord.SelectOption(
            label="Custom Profession...", value="__custom__", description="Type your own custom class and background"
        ))

        select = discord.ui.Select(placeholder=f"Choose a profession ({scenario.title()})...", options=options)
        select.callback = self._on_select
        self.add_item(select)

    async def _on_select(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your adventure setup.", ephemeral=True)
            return
        val = interaction.data["values"][0]
        if val == "__custom__":
            await interaction.response.send_modal(LoadoutCustomClassModal(self.cog, self.user_id, self.session_config))
        else:
            scenario = self.session_config.get("scenario", "fantasy")
            templates = get_class_templates(scenario)
            cls_desc = templates.get(val, {}).get("description", "")
            view = LoadoutWeaponSelectView(self.cog, self.user_id, self.session_config, val, cls_desc)
            await interaction.response.edit_message(
                content=f"Chosen Profession: **{val}**\nNow choose your starting weapon:",
                view=view, embed=None
            )

class LoadoutCustomWeaponModal(discord.ui.Modal, title="Name Your Starting Weapon"):
    weapon_name = discord.ui.TextInput(
        label="Weapon Name", placeholder="e.g. Smart-Linked SMG, Cursed Katana", max_length=60
    )
    weapon_desc = discord.ui.TextInput(
        label="Weapon Description (optional)", style=discord.TextStyle.paragraph,
        placeholder="Flavor details -- appearance, modifications, or material", max_length=200, required=False
    )

    def __init__(self, cog: "AdventureCog", user_id: int, session_config: dict, char_class: str, class_description: str):
        super().__init__()
        self.cog = cog
        self.user_id = user_id
        self.session_config = session_config
        self.char_class = char_class
        self.class_description = class_description

    async def on_submit(self, interaction: discord.Interaction):
        w_name = str(self.weapon_name).strip()
        w_desc = str(self.weapon_desc).strip()
        await interaction.response.defer(ephemeral=True)
        view = await LoadoutEquipmentPreviewView.create(
            self.cog, self.user_id, self.session_config, self.char_class, self.class_description, w_name, w_desc
        )
        embed = view.build_embed()
        await interaction.followup.send(
            content="⚔️ **Adventure Loadout Preview** — Review your gear before embarking:",
            embed=embed, view=view, ephemeral=True
        )

class LoadoutWeaponSelectView(discord.ui.View):
    def __init__(self, cog: "AdventureCog", user_id: int, session_config: dict, char_class: str, class_description: str):
        super().__init__(timeout=300)
        self.cog = cog
        self.user_id = user_id
        self.session_config = session_config
        self.char_class = char_class
        self.class_description = class_description
        scenario = session_config.get("scenario", "fantasy")

        weapons = get_starting_weapons(scenario)
        options = []
        for w in weapons[:24]:
            try:
                from mechanics.combat.items.weapons import generate_random_equipment as gen_weapon
                w_item = gen_weapon(scenario=scenario, slot="Weapon", tier=3, name=w)
                w_meta = w_item.get("metadata", {})
                arch = w_meta.get("archetype", "Weapon").replace("_", " ").title()
                hand = w_meta.get("handedness", "1H")
                mult = w_meta.get("multiplier", 1.0)
                desc = f"{arch} • {hand} • {mult}x ATK"
            except Exception:
                desc = None
            options.append(discord.SelectOption(label=w[:100], description=desc[:100] if desc else None))
        options.append(discord.SelectOption(
            label="Custom Weapon...", value="__custom__", description="Name your own custom weapon"
        ))

        select = discord.ui.Select(placeholder=f"Choose a starting weapon ({scenario.title()})...", options=options)
        select.callback = self._on_select
        self.add_item(select)

    async def _on_select(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your adventure setup.", ephemeral=True)
            return
        val = interaction.data["values"][0]
        if val == "__custom__":
            await interaction.response.send_modal(
                LoadoutCustomWeaponModal(self.cog, self.user_id, self.session_config, self.char_class, self.class_description)
            )
        else:
            await interaction.response.defer()
            view = await LoadoutEquipmentPreviewView.create(
                self.cog, self.user_id, self.session_config, self.char_class, self.class_description, val, ""
            )
            embed = view.build_embed()
            await interaction.edit_original_response(
                content="⚔️ **Adventure Loadout Preview** — Review your gear before embarking:",
                embed=embed, view=view
            )

class LoadoutEquipmentPreviewView(discord.ui.View):
    def __init__(self, cog: "AdventureCog", user_id: int, session_config: dict,
                 char_class: str, class_description: str, weapon_name: str, weapon_description: str):
        super().__init__(timeout=600)
        self.cog = cog
        self.user_id = user_id
        self.session_config = session_config
        self.char_class = char_class
        self.class_description = class_description
        self.weapon_name = weapon_name
        self.weapon_description = weapon_description

    @classmethod
    async def create(cls, cog: "AdventureCog", user_id: int, session_config: dict,
                     char_class: str, class_description: str, weapon_name: str, weapon_description: str):
        view = cls(cog, user_id, session_config, char_class, class_description, weapon_name, weapon_description)
        await view.generate_and_apply_loadout()
        return view

    async def generate_and_apply_loadout(self, force_dynamic: bool = False):
        scenario = self.session_config.get("scenario", "fantasy")
        templates = get_class_templates(scenario)
        is_custom_class = self.char_class not in templates

        char = db.get_character(self.user_id) or {}
        gender = char.get("gender", "Male")
        race = char.get("race", "Human")

        if is_custom_class:
            import game_engine.turn
            gear_map = await game_engine.turn.generate_custom_starter_gear(
                char_class=self.char_class,
                class_description=self.class_description,
                scenario=scenario,
                gender=gender,
                race=race,
                weapon_name=self.weapon_name
            )
        elif force_dynamic:
            from mechanics.combat.items import generate_starter_equipment_loadout
            gear_map = generate_starter_equipment_loadout(
                scenario=scenario,
                char_class=self.char_class,
                gender=gender,
                race=race,
                weapon_name=self.weapon_name,
                tier=3
            )
        else:
            gear_map = get_starter_gear_by_class(scenario, self.char_class, gender=gender, race=race)

        starting_items = get_starting_items(scenario, self.char_class)

        db.apply_adventure_loadout(
            user_id=self.user_id,
            scenario=scenario,
            char_class=self.char_class,
            class_description=self.class_description,
            weapon_name=self.weapon_name,
            weapon_description=self.weapon_description,
            gear_map=gear_map,
            starting_items=starting_items
        )

    def build_embed(self) -> discord.Embed:
        char = db.get_character(self.user_id)
        equipment = db.get_equipment(self.user_id)
        embed = build_character_sheet_embed(char, equipment, title_prefix="⚔️ Adventure Loadout: ")
        embed.set_footer(text="Click 'Regenerate Equipment' to re-roll starting gear, or 'Begin Adventure' to start!")
        return embed

    @discord.ui.button(label="Regenerate Equipment", style=discord.ButtonStyle.secondary, emoji="🔄", row=0)
    async def regenerate_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your setup.", ephemeral=True)
            return
        await interaction.response.defer()
        await self.generate_and_apply_loadout(force_dynamic=True)
        embed = self.build_embed()
        await interaction.edit_original_response(embed=embed, view=self)

    @discord.ui.button(label="Begin Adventure", style=discord.ButtonStyle.success, emoji="⚔️", row=0)
    async def begin_adventure_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your setup.", ephemeral=True)
            return
        await interaction.response.defer()
        for child in self.children:
            child.disabled = True
        await interaction.edit_original_response(content="🎲 Initializing adventure and entering the world...", embed=None, view=None)

        cfg = self.session_config
        capacity = 1 if cfg["mode"] == "solo" else 2
        session_id = db.create_session(
            self.user_id, cfg["mode"], capacity,
            cfg["verbosity"], cfg["dialogue"], cfg["image_gen"],
            cfg["choices_style"], interaction.channel_id,
            scenario=cfg["scenario"],
            result_display=cfg["result_display"]
        )
        session = db.get_session(session_id)
        await self.cog.launch_opening_scene(interaction, session, use_followup=True)

