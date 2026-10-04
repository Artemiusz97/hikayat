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

class ZoneSelectDropdown(discord.ui.Select):
    def __init__(self, cog: "AdventureCog", session_id: int, scen_key: str, zones_summary: list, current_loc: str = "", char_name: str = "", sync: bool = False):
        self.cog = cog
        self.session_id = session_id
        self.scen_key = scen_key
        self.zones_summary = zones_summary
        self.current_loc = current_loc
        self.char_name = char_name
        self.sync = sync

        options = []
        for z in zones_summary[:25]:
            z_name = z["zone_name"]
            desc_parts = [f"{z.get('places_count', 0)} places"]
            if z.get("is_current"):
                desc_parts.append("Current")
            if z.get("theme"):
                desc_parts.append(z["theme"])
            elif z.get("active_tags"):
                desc_parts.append(z["active_tags"][0])
            emoji = "🧭" if z.get("is_current") else z.get("emoji", "📍")
            options.append(discord.SelectOption(
                label=z_name[:100],
                value=z_name[:100],
                description=" | ".join(desc_parts)[:100],
                emoji=emoji
            ))
        if not options:
            options.append(discord.SelectOption(label="Current Area", value="Local Area", emoji="📍"))

        super().__init__(
            placeholder="🗺️ Select a region to explore...",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        selected_zone = self.values[0]
        view = PrimarySelectView(
            cog=self.cog,
            session_id=self.session_id,
            scen_key=self.scen_key,
            zone_name=selected_zone,
            zones_summary=self.zones_summary,
            current_loc=self.current_loc,
            char_name=self.char_name,
            sync=self.sync
        )
        embed = build_zone_places_embed(self.session_id, selected_zone, self.scen_key, current_loc=self.current_loc, char_name=self.char_name)
        await interaction.response.edit_message(embed=embed, view=view)

class ZoneSelectView(discord.ui.View):
    def __init__(self, cog: "AdventureCog", session_id: int, scen_key: str, current_loc: str = "", char_name: str = "", sync: bool = False, zones_summary: list = None):
        super().__init__(timeout=180)
        if zones_summary is None:
            from mechanics.world.locations import process_llm_location_update, get_zone_summary_tree, sanitize_location_target
            # Auto-discover any active quest target locations so they exist in SQLite and show in the dropdown
            active_wps = db.get_all_session_active_waypoints(session_id)
            for wp in active_wps:
                target_loc = wp.get("target_location", "").strip()
                if target_loc:
                    clean_target = sanitize_location_target(target_loc, session_id=session_id, scen_key=scen_key, char_name=char_name)
                    process_llm_location_update(session_id, clean_target, scen_key, char_name=char_name)
            zones_summary = get_zone_summary_tree(session_id, scen_key, current_loc=current_loc, char_name=char_name)

        self.add_item(ZoneSelectDropdown(cog, session_id, scen_key, zones_summary, current_loc=current_loc, char_name=char_name, sync=sync))

class PrimarySelectDropdown(discord.ui.Select):
    def __init__(self, cog: "AdventureCog", session_id: int, options_list: list, sync: bool = False):
        super().__init__(
            placeholder="📍 Select destination...",
            min_values=1,
            max_values=1,
            options=options_list
        )
        self.cog = cog
        self.session_id = session_id
        self.sync = sync

    async def callback(self, interaction: discord.Interaction):
        selected_location = self.values[0]
        action_text = f"I travel to {selected_location}."
        if self.sync:
            await self.cog.handle_sync_pick(interaction, self.session_id, custom_text=action_text)
        else:
            await self.cog.handle_action(interaction, self.session_id, custom_text=action_text)

class PrimarySelectView(discord.ui.View):
    def __init__(self, cog: "AdventureCog", session_id: int, scen_key: str, zone_name: str, zones_summary: list, current_loc: str = "", char_name: str = "", sync: bool = False):
        super().__init__(timeout=180)
        self.cog = cog
        self.session_id = session_id
        self.scen_key = scen_key
        self.zone_name = zone_name
        self.zones_summary = zones_summary
        self.current_loc = current_loc
        self.char_name = char_name
        self.sync = sync

        target_zone = next((z for z in zones_summary if z["zone_name"].lower() == zone_name.lower()), None)
        primary_items = target_zone.get("primary_locations", []) if target_zone else []

        from mechanics.world.locations import parse_tiered_location
        curr_z, _, _ = parse_tiered_location(current_loc, scen_key, session_id=session_id, char_name=char_name) if current_loc else ("", "", "")

        options = []
        for p in primary_items[:25]:
            p_name = p["name"]
            val_str = p["value"]
            emoji = p.get("archetype_emoji") or p.get("emoji") or "📍"
            is_same_zone = bool(curr_z and curr_z.lower() == zone_name.lower())
            travel_tag = "Instant Local" if is_same_zone else "Inter-Zone Travel"
            arch_label = p.get("archetype") or "Area"
            badges = p.get("badges", "")
            if badges:
                desc = f"[{travel_tag}] {arch_label} {badges}"
            else:
                desc = f"[{travel_tag}] {arch_label}"
            options.append(discord.SelectOption(
                label=p_name[:100],
                description=desc[:100],
                value=val_str[:100],
                emoji=emoji
            ))

        if not options:
            options.append(discord.SelectOption(label=f"{zone_name} Main Area", value=f"{zone_name} ➔ Main Area", emoji="📍"))

        self.add_item(PrimarySelectDropdown(cog, session_id, options, sync=sync))

        # Back button to return to World Map view
        back_btn = discord.ui.Button(label="World Map", emoji="🗺️", style=discord.ButtonStyle.secondary)
        back_btn.callback = self._on_back
        self.add_item(back_btn)

    async def _on_back(self, interaction: discord.Interaction):
        embed = build_world_map_embed(self.session_id, self.scen_key, current_loc=self.current_loc, char_name=self.char_name)
        view = ZoneSelectView(self.cog, self.session_id, self.scen_key, current_loc=self.current_loc, char_name=self.char_name, sync=self.sync)
        await interaction.response.edit_message(embed=embed, view=view)

class SceneItemSelectDropdown(discord.ui.Select):
    def __init__(self, cog: "AdventureCog", session_id: int, user_id: int, items: list[dict], sync: bool = False):
        self.cog = cog
        self.session_id = session_id
        self.user_id = user_id
        self.sync = sync
        self.items = items

        options = []
        seen = set()
        for item in items[:25]:
            name = item["name"]
            if name in seen:
                continue
            seen.add(name)
            icon = get_item_icon(name, item.get("item_type", ""), item.get("effect", ""))
            desc = item.get("effect") or f"Type: {item.get('item_type', 'Item')}"
            options.append(discord.SelectOption(
                label=f"{name}"[:100],
                value=str(item["id"]),
                description=desc[:100],
                emoji=icon
            ))
        super().__init__(placeholder="Choose an item from your bag...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        item_id = int(self.values[0])
        inv = db.get_inventory(self.user_id)
        selected_item = next((i for i in inv if i["id"] == item_id), None)
        if not selected_item:
            await interaction.response.send_message("❌ Item no longer in inventory.", ephemeral=True)
            return

        session = db.get_session(self.session_id)
        if not session:
            await interaction.response.send_message("❌ Session not found.", ephemeral=True)
            return

        targets = [{"label": "🧑 Yourself (Self)", "name": "Yourself", "type": "self"}]

        # Friendly Companions in scene
        for npc in (session.get("current_npcs") or []):
            if isinstance(npc, dict) and npc.get("name"):
                disp = str(npc.get("disposition", "")).lower()
                is_comp = npc.get("hp") is not None or disp in ("friendly", "companion", "ally")
                prefix = "⭐" if is_comp else "👤"
                role_tag = "Companion" if is_comp else "NPC"
                targets.append({
                    "label": f"{prefix} {npc['name']} ({role_tag})",
                    "name": npc["name"],
                    "type": "companion" if is_comp else "npc"
                })

        # Other party members (multiplayer)
        for uid in session.get("turn_order", []):
            if uid != self.user_id:
                p_char = db.get_character(uid)
                if p_char:
                    targets.append({
                        "label": f"🛡️ {p_char['name']} (Party Member)",
                        "name": p_char["name"],
                        "type": "player"
                    })

        # Hostile Enemies in scene
        for m in (session.get("nearby_enemies", [])):
            if isinstance(m, dict) and m.get("name"):
                targets.append({
                    "label": f"👹 {m['name']} (Enemy - ❤️ {m.get('hp', '?')})",
                    "name": m["name"],
                    "type": "enemy"
                })

        # Environment
        targets.append({
            "label": "💥 The Ground / Surrounding Area",
            "name": "the surrounding ground/environment",
            "type": "environment"
        })

        view = SceneUniversalTargetSelectView(self.cog, self.session_id, self.user_id, selected_item, targets, self.sync)
        await interaction.response.edit_message(
            content=f"🎯 Choose who or what to use **{selected_item['name']}** on:",
            view=view
        )

class SceneItemSelectView(discord.ui.View):
    def __init__(self, cog: "AdventureCog", session_id: int, user_id: int, items: list[dict], sync: bool = False):
        super().__init__(timeout=120)
        self.add_item(SceneItemSelectDropdown(cog, session_id, user_id, items, sync=sync))

class SceneUniversalTargetSelectDropdown(discord.ui.Select):
    def __init__(self, cog: "AdventureCog", session_id: int, user_id: int, item: dict, targets: list[dict], sync: bool = False):
        self.cog = cog
        self.session_id = session_id
        self.user_id = user_id
        self.item = item
        self.targets = targets
        self.sync = sync

        options = []
        for idx, t in enumerate(targets[:25]):
            options.append(discord.SelectOption(
                label=t["label"][:100],
                value=str(idx),
                description=f"Use {item['name']} on {t['name']}"[:100]
            ))
        super().__init__(placeholder="Select target in the scene...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        idx = int(self.values[0])
        target = self.targets[idx]
        target_name = target["name"]
        item_name = self.item["name"]
        from mechanics.combat.items import parse_item_effect, is_giftable_item
        parsed_category = parse_item_effect(self.item).get("category", "utility")
        if parsed_category == "throwable" and target["type"] in ("enemy", "monster", "npc", "environment"):
            action_text = f"Throw {item_name} at {target_name}."
        elif target["type"] == "self":
            action_text = f"Use {item_name} on myself."
        elif target["type"] in ("companion", "npc", "player") and is_giftable_item(self.item):
            action_text = f"Give {item_name} as a gift to {target_name}."
        else:
            action_text = f"Use {item_name} on {target_name}."

        await interaction.response.edit_message(content=f"🎒 Action locked in: *{action_text}*", view=None)

        if self.sync:
            await self.cog.handle_sync_pick(
                interaction, self.session_id,
                custom_text=action_text,
                is_item_action=True,
                item_name=item_name,
                target_name=target_name
            )
        else:
            await self.cog.handle_action(
                interaction, self.session_id,
                custom_text=action_text,
                is_item_action=True,
                item_name=item_name,
                target_name=target_name
            )

class SceneUniversalTargetSelectView(discord.ui.View):
    def __init__(self, cog: "AdventureCog", session_id: int, user_id: int, item: dict, targets: list[dict], sync: bool = False):
        super().__init__(timeout=120)
        self.add_item(SceneUniversalTargetSelectDropdown(cog, session_id, user_id, item, targets, sync=sync))

