from .constants import *
import asyncio
import json
import logging
import random
import re
import time
import discord
from .locations import PrimarySelectView
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

class CustomActionModal(discord.ui.Modal, title="Do Something Else"):
    action = discord.ui.TextInput(
        label="What do you do?", style=discord.TextStyle.paragraph,
        placeholder="Describe your action in the scene...", max_length=300,
    )

    def __init__(self, cog: "AdventureCog", session_id: int, sync: bool):
        super().__init__()
        self.cog = cog
        self.session_id = session_id
        self.sync = sync

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.response.is_done():
            try:
                await interaction.response.defer()
            except (discord.NotFound, discord.HTTPException):
                pass

        if self.sync:
            await self.cog.handle_sync_pick(interaction, self.session_id, custom_text=str(self.action))
        else:
            await self.cog.handle_action(interaction, self.session_id, custom_text=str(self.action))

class ChoiceDropdown(discord.ui.Select):
    def __init__(self, cog: "AdventureCog", session_id: int, choices: list, actor_char: dict = None, is_sync: bool = False, turn_user_id: int = None, party: list = None):
        self.cog = cog
        self.session_id = session_id
        self.is_sync = is_sync
        self.turn_user_id = turn_user_id
        self.party = party
        
        options = []
        session = (db.get_session(session_id) if session_id else {}) or {}
        actor_uid = (actor_char.get("user_id") or actor_char.get("id")) if actor_char else None
        actor_settings = db.get_settings(actor_uid) if actor_uid else {}
        show_percentages = bool(actor_settings.get("show_percentages", session.get("show_percentages", 1))) if actor_char else bool(session.get("show_percentages", 1))

        for idx, choice in enumerate(choices[:24]):
            raw_text = choice.get("label", "")
            stat = choice.get("stat", "AGI")
            
            # --- CODE-DRIVEN PRE-FORMATTED CHOICE HANDLING ---
            if "%" in raw_text:
                full_label = raw_text.strip()
                first_char = full_label[0] if full_label else ""
                opt_emoji = None
                if ord(first_char) > 255:
                    opt_emoji = first_char
                    full_label = full_label[1:].strip()
                else:
                    opt_emoji = STAT_EMOJI.get(stat, "❔")
                    
                if not show_percentages:
                    import re
                    full_label = re.sub(r'\b\d+%\s*', '', full_label).strip()

                desc = ""
                if len(full_label) > 42:
                    split_idx = full_label.rfind(" ", 0, 42)
                    if split_idx == -1:
                        split_idx = 42
                    desc = "..." + full_label[split_idx:].strip()
                    full_label = full_label[:split_idx] + "..."
                if desc and len(desc) > 100:
                    desc = desc[:97] + "..."

                options.append(discord.SelectOption(
                    label=full_label[:100],
                    value=str(idx),
                    description=desc if desc else None,
                    emoji=opt_emoji
                ))
                continue

            # --- STANDARD NON-COMBAT / EXPLORATION CHOICE HANDLING ---
            raw_lower = raw_text.lower()
            is_free = (stat in ("NONE", "FREE", "ITEM") or choice.get("requirement", 0) <= 0)
            
            quest_icon = _get_choice_quest_icon(choice)
            skill_emoji = _get_choice_skill_emoji(choice)
            opt_emoji = quest_icon or skill_emoji
            
            if is_sync and party:
                if is_free:
                    chance_str = "100%"
                else:
                    stat_col = STAT_COLUMN.get(stat, "agi_")
                    chance_str = "/".join(f"{char['name']} {success_chance(char.get(stat_col, 5), choice['requirement'])}%" for char, _ in party)
            else:
                if is_free:
                    chance_str = "100%"
                else:
                    actor_settings = db.get_settings(actor_char["user_id"]) if actor_char else {}
                    check_mode = actor_settings.get("debug_check_mode", "off")
                    stat_col = STAT_COLUMN.get(stat, "agi_")
                    chance = success_chance(actor_char.get(stat_col, 5), choice["requirement"], check_mode=check_mode) if actor_char else 50
                    chance_str = f"{chance}%"
                
            prefix = f"{chance_str} " if show_percentages else ""
            
            mp_cost = choice.get("mp_cost", 0)
            mp_str = f" 💙 {mp_cost} MP" if mp_cost > 0 else ""
            
            clean_raw_text = _strip_leading_emojis(raw_text)
            if quest_icon and not is_free:
                full_label = f"{prefix}{skill_emoji} [{stat}] {clean_raw_text}"
            elif not is_free:
                full_label = f"{prefix}[{stat}] {clean_raw_text}"
            else:
                full_label = f"{prefix}{clean_raw_text}"

            desc = ""
            if len(full_label) > 42:
                split_idx = full_label.rfind(" ", 0, 42)
                if split_idx == -1:
                    split_idx = 42
                desc = "..." + full_label[split_idx:].strip()
                if mp_str:
                    desc = f"{desc}{mp_str}"
                full_label = full_label[:split_idx] + "..."
            elif mp_cost > 0:
                desc = mp_str.strip()
                
            if desc and len(desc) > 100:
                desc = desc[:97] + "..."
                
            options.append(discord.SelectOption(
                label=full_label[:100],
                value=str(idx),
                description=desc if desc else None,
                emoji=opt_emoji
            ))

        if not options:
            options.append(discord.SelectOption(
                label="Proceed forward",
                value="0",
                description="Continue your adventure"
            ))

        super().__init__(placeholder="Choose your action...", min_values=1, max_values=1, options=options)
        
    async def callback(self, interaction: discord.Interaction):
        idx = int(self.values[0])
        if self.is_sync:
            await self.cog.handle_sync_pick(interaction, self.session_id, choice_index=idx)
        else:
            if interaction.user.id != self.turn_user_id:
                await interaction.response.send_message(f"It's not your turn — waiting on <@{self.turn_user_id}>.", ephemeral=True)
                return
            await self.cog.handle_action(interaction, self.session_id, choice_index=idx)

class ChoiceView(discord.ui.View):
    """Turn-based (and solo) mode: only the current turn-holder can act."""

    def __init__(self, cog: "AdventureCog", session_id: int, turn_user_id: int, choices: list, actor_char: dict,
                 merchant: dict = None, current_menu: str = "root"):
        super().__init__(timeout=86400)
        self.cog = cog
        self.session_id = session_id
        self.turn_user_id = turn_user_id
        self.choices = choices
        self.actor_char = actor_char
        self.merchant = merchant or {}
        self.current_menu = current_menu

        session = db.get_session(session_id) or {}
        self.session = session
        scen_key = session.get("scenario", "fantasy")
        from mechanics.combat import is_in_combat
        self.in_combat = is_in_combat(session)

        if self.in_combat:
            from mechanics.narrative.choice_generator import generate_categorized_combat_actions
            inv = db.get_inventory(turn_user_id) if turn_user_id else []
            party_loadout = [(actor_char, inv)]
            hostiles = session.get("nearby_enemies", [])
            self.hostiles = [m for m in hostiles if isinstance(m, dict) and m.get("hp", 1) > 0]
            if not hasattr(self, "target_idx") or self.target_idx >= len(self.hostiles):
                self.target_idx = 0
            monster = self.hostiles[self.target_idx] if self.hostiles else (hostiles[0] if hostiles else {"name": "Enemy", "stats": {}})
            current_loc = session.get("current_location", "area") if session else "area"
            self.categorized = generate_categorized_combat_actions(party_loadout, monster, current_loc, scen_key)

            actor_settings = db.get_settings(turn_user_id) if turn_user_id else {}
            combat_style = actor_settings.get("combat_ui_style", session.get("combat_ui_style", "battle_deck") if session else "battle_deck")

            if combat_style == "multi_dropdown":
                self._build_multi_dropdown_combat()
            else:
                self._prebuild_battle_deck_menus()
                self._build_battle_deck_combat(current_menu)
            return

        curr_narr = str(session.get("narrative") or "")
        is_fallback_narr = (
            ("The atmosphere settles around" in curr_narr and "awaiting the party's next move" in curr_narr)
            or ("acts with deliberate intent:" in curr_narr)
            or bool(session.get("is_fallback_generation"))
        )
        is_fb = any(choice.get("is_fallback") for choice in choices) or is_fallback_narr

        self.add_item(ChoiceDropdown(cog, session_id, choices, actor_char, is_sync=False, turn_user_id=turn_user_id))

        if is_fb:
            retry_button = discord.ui.Button(label="Retry generation",
                                              style=discord.ButtonStyle.secondary, emoji="🔄")
            retry_button.callback = self._retry_callback
            self.add_item(retry_button)

        custom_button = discord.ui.Button(label="Do something else...",
                                           style=discord.ButtonStyle.secondary, emoji="✏️")
        custom_button.callback = self._custom_callback
        self.add_item(custom_button)

        use_item_button = discord.ui.Button(label="Use Item",
                                            style=discord.ButtonStyle.secondary, emoji="🎒")
        use_item_button.callback = self._use_item_callback
        self.add_item(use_item_button)

        from mechanics.system.phone import scenario_has_smartphone, get_phone_branding, build_phone_home_embed, PhoneMainView
        if scenario_has_smartphone(scen_key) and not self.in_combat:
            branding = get_phone_branding(scen_key)
            phone_btn = discord.ui.Button(label=branding["device_name"].split(" ", 1)[-1], emoji=branding["emoji"], style=discord.ButtonStyle.secondary)
            phone_btn.callback = self._phone_callback
            self.add_item(phone_btn)

        if is_location_engine_enabled(scen_key) and not self.in_combat:
            move_button = discord.ui.Button(label="Move Location", style=discord.ButtonStyle.secondary, emoji="📍")
            move_button.callback = self._move_location_callback
            self.add_item(move_button)

        from scenario_data import is_mechanic_enabled
        party_npcs = (session.get("party_npcs") if session else None) or []
        if party_npcs and not self.in_combat:
            btn_lbl = "Party" if is_mechanic_enabled(scen_key, "tactical_combat") else "Companions"
            party_btn = discord.ui.Button(label=btn_lbl, style=discord.ButtonStyle.secondary, emoji="💬")
            party_btn.callback = self._party_dialogue_callback
            self.add_item(party_btn)

        current_loc = session.get("current_location", "") if session else ""
        from mechanics.world.locations import location_has_bounty_board, get_notice_board_label
        if location_has_bounty_board(current_loc, scen_key=scen_key) and not self.in_combat:
            nb_label, nb_emoji = get_notice_board_label(scen_key)
            notice_button = discord.ui.Button(label=nb_label, style=discord.ButtonStyle.secondary, emoji=nb_emoji)
            notice_button.callback = self._notice_board_callback
            self.add_item(notice_button)

        from mechanics.world.locations import location_has_merchant_shop, is_school_scenario
        is_school = is_school_scenario(scen_key)
        show_merchant = False
        merchant_label = "Talk to Merchant"
        if is_school:
            if location_has_merchant_shop(current_loc, scen_key=scen_key):
                show_merchant = True
                merchant_label = "Visit Shop / Café"
        else:
            has_shop = location_has_merchant_shop(current_loc, scen_key=scen_key)
            if self.merchant.get("available") or has_shop:
                show_merchant = True
                merchant_label = "Visit Market / Shop" if has_shop else "Talk to Merchant"

        if show_merchant and not self.in_combat:
            merchant_button = discord.ui.Button(label=merchant_label,
                                                 style=discord.ButtonStyle.success, emoji="🛍️")
            merchant_button.callback = self._talk_to_merchant
            self.add_item(merchant_button)

        faction = db.get_faction_by_hq(session_id, current_loc)
        if faction and not self.in_combat:
            hq_button = discord.ui.Button(label=f"Enter {faction.get('name', 'HQ')}", style=discord.ButtonStyle.primary, emoji="🏛️")
            hq_button.callback = self._faction_hq_callback
            self.add_item(hq_button)

        # Dynamic Conversant Profile Shortcut Button
        from scenario_data import is_mechanic_enabled
        if not self.in_combat and (is_mechanic_enabled(scen_key, "contact_list") or is_mechanic_enabled(scen_key, "relationship_meter")):
            from mechanics.world.mobility import get_session_dialogue_partners
            dialogue_partners = get_session_dialogue_partners(session)
            if dialogue_partners:
                char_id = actor_char.get("id", 0) if actor_char else 0
                contacts = db.get_contacts(session_id, character_id=char_id)
                matching_contacts = []
                for dp in dialogue_partners:
                    for c in contacts:
                        if is_matching_contact_dialogue_partner(c, dp):
                            if not any(mc.get("name") == c.get("name") for mc in matching_contacts):
                                matching_contacts.append(c)
                for contact in matching_contacts:
                    c_name = str(contact.get("name") or "Contact").strip()
                    first_name = c_name.split()[0] if c_name else "Contact"
                    label_name = first_name if len(c_name) > 15 else c_name
                    profile_btn = discord.ui.Button(
                        label=f"Profile: {label_name}"[:80],
                        style=discord.ButtonStyle.secondary,
                        emoji="👤"
                    )
                    profile_btn.callback = self._make_contact_profile_callback(contact)
                    self.add_item(profile_btn)

    def _prebuild_battle_deck_menus(self):
        """Option 2: Pre-build ALL menu item sets once at construction time.

        Stores lists of (item_object, callback) tuples keyed by menu name in
        self._menu_items so that _switch_menu can attach them instantly at
        click time with no button-construction work."""
        attacks = self.categorized.get("attacks", [])
        magic = self.categorized.get("magic", [])
        tactics = self.categorized.get("tactics", [])
        weapon_name = self.categorized.get("weapon_name", "Fists")
        player_mp = self.actor_char.get("mp", 0)

        # ── root menu ────────────────────────────────────────────────────────
        root_items = []

        atk_btn = discord.ui.Button(label=f"Attack ({weapon_name})", emoji="⚔️", style=discord.ButtonStyle.primary, row=0)
        atk_btn.callback = self._switch_menu("attacks")
        root_items.append(atk_btn)

        magic_style = discord.ButtonStyle.primary if player_mp >= 6 else discord.ButtonStyle.secondary
        magic_btn = discord.ui.Button(label=f"Magic ({player_mp} MP)", emoji="🔮", style=magic_style, row=0)
        magic_btn.callback = self._switch_menu("magic")
        root_items.append(magic_btn)

        tactics_btn = discord.ui.Button(label="Tactics & Skills", emoji="🧠", style=discord.ButtonStyle.secondary, row=0)
        tactics_btn.callback = self._switch_menu("tactics")
        root_items.append(tactics_btn)

        flee_btn = discord.ui.Button(label="Flee Battle", emoji="🏃", style=discord.ButtonStyle.danger, row=1)
        flee_btn.callback = self._flee_callback
        root_items.append(flee_btn)

        use_item_button = discord.ui.Button(label="Use Item", style=discord.ButtonStyle.secondary, emoji="🎒", row=1)
        use_item_button.callback = self._use_item_callback
        root_items.append(use_item_button)

        custom_button = discord.ui.Button(label="Do something else...", style=discord.ButtonStyle.secondary, emoji="✏️", row=1)
        custom_button.callback = self._custom_callback
        root_items.append(custom_button)

        if hasattr(self, "hostiles") and len(self.hostiles) > 1:
            cur_target = self.hostiles[self.target_idx]
            target_hp = cur_target.get("hp", 100)
            target_max = cur_target.get("max_hp", 100)
            target_btn = discord.ui.Button(
                label=f"Target: {cur_target.get('name', 'Enemy')} ({target_hp}/{target_max})"[:80],
                emoji="🎯",
                style=discord.ButtonStyle.secondary,
                row=2
            )
            target_btn.callback = self._switch_target_callback
            root_items.append(target_btn)

        # ── attacks menu ─────────────────────────────────────────────────────
        attack_items = []
        for idx, atk in enumerate(attacks[:4]):
            btn = discord.ui.Button(label=atk.get("label", "Attack")[:80], style=discord.ButtonStyle.primary, row=idx // 2)
            btn.callback = self._make_direct_choice_callback(atk)
            attack_items.append(btn)
        back_btn = discord.ui.Button(label="Back to Battle Menu", emoji="⬅️", style=discord.ButtonStyle.secondary, row=2)
        back_btn.callback = self._switch_menu("root")
        attack_items.append(back_btn)

        # ── magic menu ───────────────────────────────────────────────────────
        magic_items = []
        for idx, sp in enumerate(magic[:8]):
            mp_cost = sp.get("mp_cost", 0)
            can_cast = player_mp >= mp_cost
            btn = discord.ui.Button(
                label=sp.get("label", "Spell")[:80],
                style=discord.ButtonStyle.primary if can_cast else discord.ButtonStyle.secondary,
                disabled=not can_cast,
                row=min(3, idx // 2)
            )
            btn.callback = self._make_direct_choice_callback(sp)
            magic_items.append(btn)
        back_btn = discord.ui.Button(label="Back to Battle Menu", emoji="⬅️", style=discord.ButtonStyle.secondary, row=4)
        back_btn.callback = self._switch_menu("root")
        magic_items.append(back_btn)

        # ── tactics menu ─────────────────────────────────────────────────────
        tactics_items = []
        for idx, tac in enumerate(tactics[:4]):
            btn = discord.ui.Button(label=tac.get("label", "Tactic")[:80], style=discord.ButtonStyle.secondary, row=idx // 2)
            btn.callback = self._make_direct_choice_callback(tac)
            tactics_items.append(btn)
        back_btn = discord.ui.Button(label="Back to Battle Menu", emoji="⬅️", style=discord.ButtonStyle.secondary, row=2)
        back_btn.callback = self._switch_menu("root")
        tactics_items.append(back_btn)

        self._menu_items = {
            "root": root_items,
            "attacks": attack_items,
            "magic": magic_items,
            "tactics": tactics_items,
        }

    def _build_battle_deck_combat(self, current_menu: str = "root"):
        """Attach the pre-built item set for current_menu.

        Option 2: all button objects are already constructed in self._menu_items;
        this method just clears the view and re-attaches the cached set — no
        button construction happens at click time."""
        self.clear_items()
        self.current_menu = current_menu
        for item in self._menu_items.get(current_menu, self._menu_items["root"]):
            self.add_item(item)

    def _build_multi_dropdown_combat(self):
        self.clear_items()
        attacks = self.categorized.get("attacks", [])
        magic = self.categorized.get("magic", [])
        tactics = self.categorized.get("tactics", [])
        player_mp = self.actor_char.get("mp", 0)

        if attacks:
            atk_options = [
                discord.SelectOption(label=a.get("label", "Attack")[:100], value=str(i), emoji="⚔️")
                for i, a in enumerate(attacks[:5])
            ]
            atk_select = discord.ui.Select(placeholder="⚔️ Basic Attacks...", options=atk_options, row=0)
            atk_select.callback = self._make_dropdown_action_callback(attacks)
            self.add_item(atk_select)

        if magic:
            mag_options = [
                discord.SelectOption(
                    label=m.get("label", "Spell")[:100],
                    value=str(i),
                    emoji="🔮" if m.get("discipline") == "attack" else ("💚" if m.get("discipline") == "support" else "💀"),
                    description=None if player_mp >= m.get("mp_cost", 0) else f"Needs {m.get('mp_cost')} MP"
                )
                for i, m in enumerate(magic[:10])
            ]
            mag_select = discord.ui.Select(placeholder=f"🔮 Magic & Spells ({player_mp} MP)...", options=mag_options, row=1)
            mag_select.callback = self._make_dropdown_action_callback(magic)
            self.add_item(mag_select)

        if tactics:
            tac_options = [
                discord.SelectOption(label=t.get("label", "Tactic")[:100], value=str(i), emoji="🧠")
                for i, t in enumerate(tactics[:5])
            ]
            tac_select = discord.ui.Select(placeholder="🧠 Tactics & Environment...", options=tac_options, row=2)
            tac_select.callback = self._make_dropdown_action_callback(tactics)
            self.add_item(tac_select)

        flee_btn = discord.ui.Button(label="Flee Battle", emoji="🏃", style=discord.ButtonStyle.danger, row=3)
        flee_btn.callback = self._flee_callback
        self.add_item(flee_btn)

        use_item_button = discord.ui.Button(label="Use Item", style=discord.ButtonStyle.secondary, emoji="🎒", row=3)
        use_item_button.callback = self._use_item_callback
        self.add_item(use_item_button)

        custom_button = discord.ui.Button(label="Do something else...", style=discord.ButtonStyle.secondary, emoji="✏️", row=3)
        custom_button.callback = self._custom_callback
        self.add_item(custom_button)

        if hasattr(self, "hostiles") and len(self.hostiles) > 1:
            cur_target = self.hostiles[self.target_idx]
            target_hp = cur_target.get("hp", 100)
            target_max = cur_target.get("max_hp", 100)
            target_btn = discord.ui.Button(
                label=f"Target: {cur_target.get('name', 'Enemy')} ({target_hp}/{target_max})"[:80],
                emoji="🎯",
                style=discord.ButtonStyle.secondary,
                row=4
            )
            target_btn.callback = self._switch_target_callback
            self.add_item(target_btn)

    async def _switch_target_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.turn_user_id:
            await interaction.response.send_message(f"It's not your turn — waiting on <@{self.turn_user_id}>.", ephemeral=True)
            return
        # Option 1: acknowledge immediately so Discord un-greys buttons at once.
        await interaction.response.defer()
        if hasattr(self, "hostiles") and len(self.hostiles) > 1:
            self.target_idx = (self.target_idx + 1) % len(self.hostiles)
            monster = self.hostiles[self.target_idx]
            inv = db.get_inventory(self.turn_user_id) if self.turn_user_id else []
            party_loadout = [(self.actor_char, inv)]
            current_loc = self.session.get("current_location", "area") if self.session else "area"
            scen_key = self.session.get("scenario", "fantasy")
            from mechanics.narrative.choice_generator import generate_categorized_combat_actions
            self.categorized = generate_categorized_combat_actions(party_loadout, monster, current_loc, scen_key)

            actor_settings = db.get_settings(self.turn_user_id) if self.turn_user_id else {}
            combat_style = actor_settings.get("combat_ui_style", self.session.get("combat_ui_style", "battle_deck") if self.session else "battle_deck")
            if combat_style == "multi_dropdown":
                self._build_multi_dropdown_combat()
            else:
                # Rebuild the cache for the new target, then swap to current menu.
                self._prebuild_battle_deck_menus()
                self._build_battle_deck_combat(getattr(self, "current_menu", "root"))
            await interaction.edit_original_response(view=self)

    def _switch_menu(self, menu_name: str):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.turn_user_id:
                await interaction.response.send_message(f"It's not your turn — waiting on <@{self.turn_user_id}>.", ephemeral=True)
                return
            # Option 1: acknowledge immediately — buttons un-grey at once.
            # Option 2: _build_battle_deck_combat just swaps from pre-built cache, no construction work.
            await interaction.response.defer()
            self._build_battle_deck_combat(current_menu=menu_name)
            await interaction.edit_original_response(view=self)
        return callback

    def _make_direct_choice_callback(self, choice_dict: dict):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.turn_user_id:
                await interaction.response.send_message(f"It's not your turn — waiting on <@{self.turn_user_id}>.", ephemeral=True)
                return
            await self.cog.handle_action(interaction, self.session_id, direct_choice=choice_dict)
        return callback

    def _make_dropdown_action_callback(self, action_list: list):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.turn_user_id:
                await interaction.response.send_message(f"It's not your turn — waiting on <@{self.turn_user_id}>.", ephemeral=True)
                return
            vals = interaction.data.get("values", [])
            idx = int(vals[0]) if vals else 0
            if 0 <= idx < len(action_list):
                chosen = action_list[idx]
                await self.cog.handle_action(interaction, self.session_id, direct_choice=chosen)
        return callback

    async def _flee_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.turn_user_id:
            await interaction.response.send_message(f"It's not your turn — waiting on <@{self.turn_user_id}>.", ephemeral=True)
            return
        flee_action = getattr(self, "categorized", {}).get("flee")
        if not flee_action:
            flee_action = {
                "label": "🏃 Disengage & Flee from battle",
                "stat": "AGI",
                "requirement": 6,
                "mp_cost": 0,
                "choice_type": "EVADE_TACTICAL_FLEE",
                "action_category": "flee"
            }
        await self.cog.handle_action(interaction, self.session_id, direct_choice=flee_action)

    def _make_callback(self, idx: int):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.turn_user_id:
                await interaction.response.send_message(
                    f"It's not your turn — waiting on <@{self.turn_user_id}>.", ephemeral=True)
                return
            await self.cog.handle_action(interaction, self.session_id, choice_index=idx)
        return callback

    async def _custom_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.turn_user_id:
            await interaction.response.send_message(
                f"It's not your turn — waiting on <@{self.turn_user_id}>.", ephemeral=True)
            return
        await interaction.response.send_modal(CustomActionModal(self.cog, self.session_id, sync=False))

    async def _use_item_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.turn_user_id:
            await interaction.response.send_message(
                f"It's not your turn — waiting on <@{self.turn_user_id}>.", ephemeral=True)
            return
        inv = db.get_inventory(interaction.user.id)
        carried = [i for i in inv if not i.get("equipped")]
        if not carried:
            await interaction.response.send_message("❌ You have no carried items in your inventory.", ephemeral=True)
            return
        view = SceneItemSelectView(self.cog, self.session_id, interaction.user.id, carried, sync=False)
        await interaction.response.send_message("🎒 Select an item from your bag to use:", view=view, ephemeral=True)

    async def _move_location_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.turn_user_id:
            msg = f"It's not your turn — waiting on <@{self.turn_user_id}>."
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
            return

        # Defer immediately to avoid Discord's 3-second interaction timeout & race conditions
        if not interaction.response.is_done():
            try:
                await interaction.response.defer(ephemeral=True)
            except (discord.HTTPException, discord.NotFound):
                pass

        session = db.get_session(self.session_id)
        from mechanics.combat import is_in_combat
        if is_in_combat(session):
            msg = "❌ **Cannot travel while engaged in combat!** Defeat your enemies or flee first."
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
            return
        scen_key = session.get("scenario", "fantasy") if session else "fantasy"
        cur_loc = session.get("current_location", "")
        char = db.get_character(interaction.user.id)
        char_name = char.get("name", "") if char else ""

        from mechanics.world.locations import parse_tiered_location, get_zone_summary_tree, process_llm_location_update, sanitize_location_target
        # Auto-discover any active quest target locations
        active_wps = db.get_all_session_active_waypoints(self.session_id)
        for wp in active_wps:
            target_loc = wp.get("target_location", "").strip()
            if target_loc:
                clean_target = sanitize_location_target(target_loc, session_id=self.session_id, scen_key=scen_key, char_name=char_name)
                process_llm_location_update(self.session_id, clean_target, scen_key, char_name=char_name)

        curr_z, _, _ = parse_tiered_location(cur_loc, scen_key, session_id=self.session_id, char_name=char_name)
        zones_summary = get_zone_summary_tree(self.session_id, scen_key, current_loc=cur_loc, char_name=char_name)
        
        # Directly open the regional places view for the player's current zone
        embed = build_zone_places_embed(self.session_id, curr_z, scen_key, current_loc=cur_loc, char_name=char_name)
        view = PrimarySelectView(self.cog, self.session_id, scen_key, zone_name=curr_z, zones_summary=zones_summary, current_loc=cur_loc, char_name=char_name, sync=False)
        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        except discord.HTTPException as e:
            if getattr(e, "code", None) == 40060:
                await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            else:
                raise

    async def _phone_callback(self, interaction: discord.Interaction):
        from mechanics.system.phone import build_phone_home_embed, PhoneMainView
        embed = build_phone_home_embed(self.session_id, interaction.user.id)
        view = PhoneMainView(self.cog, self.session_id, interaction.user.id)
        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        except discord.HTTPException as e:
            if getattr(e, "code", None) == 40060:
                await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            else:
                raise

    def _make_contact_profile_callback(self, contact: dict):
        async def _profile_callback(interaction: discord.Interaction):
            from cogs.contacts import build_contact_detail_embed, ContactView
            session = db.get_session(self.session_id) or {}
            scen_key = session.get("scenario", "fantasy")
            embed = build_contact_detail_embed(contact, scen_key, user_id=interaction.user.id)
            char = db.get_character(interaction.user.id)
            char_id = char.get("id", 0) if char else 0
            contacts = db.get_contacts(self.session_id, character_id=char_id)
            view = ContactView(
                contacts, scen_key, interaction.user.id,
                active_contact=contact,
                session_id=self.session_id, cog=self.cog
            )
            try:
                if interaction.response.is_done():
                    await interaction.followup.send(embed=embed, view=view, ephemeral=True)
                else:
                    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            except discord.HTTPException as e:
                if getattr(e, "code", None) == 40060:
                    await interaction.followup.send(embed=embed, view=view, ephemeral=True)
                else:
                    raise
        return _profile_callback

    async def _notice_board_callback(self, interaction: discord.Interaction):
        session = db.get_session(self.session_id)
        if not session:
            await interaction.response.send_message("Session not found.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        bounties = await game_engine.generate_bounty_board(session)
        embed = _build_bounty_board_embed(session, bounties)
        view = BountyBoardView(session, bounties)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    async def _retry_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.turn_user_id:
            await interaction.response.send_message(
                f"It's not your turn — waiting on <@{self.turn_user_id}>.", ephemeral=True)
            return
        await self.cog.handle_retry(interaction, self.session_id)

    async def _talk_to_merchant(self, interaction: discord.Interaction):
        # Deliberately NOT gated by self.turn_user_id -- see
        # _handle_talk_to_merchant's docstring for why.
        await _handle_talk_to_merchant(self.cog, self.session_id, interaction)

    async def _faction_hq_callback(self, interaction: discord.Interaction):
        # NOT gated by turn order so anyone can open the HQ menu
        await self.cog.open_faction_hq_menu(interaction, self.session_id, interaction.user.id)

    async def _party_dialogue_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.turn_user_id:
            await interaction.response.send_message(
                f"It's not your turn — waiting on <@{self.turn_user_id}>.", ephemeral=True)
            return
        party_npcs = db.get_session_party_npcs(self.session_id)
        if not party_npcs:
            await interaction.response.send_message("You have no companions in your party.", ephemeral=True)
            return
        embed = discord.Embed(
            title="🤝 Party Companions",
            description="Select a companion to speak with or manage:",
            color=discord.Color.teal()
        )
        view = PartyDialogueSelectView(self.cog, self.session_id, interaction.user.id, sync=False)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

class SyncChoiceView(discord.ui.View):
    """Synchronized mode: every party member picks independently; nobody
    sees anyone else's pick until everyone has locked one in."""

    def __init__(self, cog: "AdventureCog", session_id: int, member_ids: list, choices: list, party: list,
                 merchant: dict = None):
        super().__init__(timeout=86400)
        self.cog = cog
        self.session_id = session_id
        self.member_ids = member_ids
        self.merchant = merchant or {}
        self.party = party

        session = db.get_session(session_id) or {}
        curr_narr = str(session.get("narrative") or "")
        is_fallback_narr = (
            ("The atmosphere settles around" in curr_narr and "awaiting the party's next move" in curr_narr)
            or ("acts with deliberate intent:" in curr_narr)
            or bool(session.get("is_fallback_generation"))
        )
        is_fb = any(choice.get("is_fallback") for choice in choices) or is_fallback_narr
        
        self.add_item(ChoiceDropdown(cog, session_id, choices, is_sync=True, party=party))

        if is_fb:
            retry_button = discord.ui.Button(label="Retry generation",
                                              style=discord.ButtonStyle.secondary, emoji="🔄")
            retry_button.callback = self._retry_callback
            self.add_item(retry_button)

        custom_button = discord.ui.Button(label="Do something else...",
                                           style=discord.ButtonStyle.secondary, emoji="✏️")
        custom_button.callback = self._custom_callback
        self.add_item(custom_button)

        use_item_button = discord.ui.Button(label="Use Item",
                                            style=discord.ButtonStyle.secondary, emoji="🎒")
        use_item_button.callback = self._use_item_callback
        self.add_item(use_item_button)

        session = db.get_session(session_id) or {}
        scen_key = session.get("scenario", "fantasy")
        from mechanics.combat import is_in_combat
        in_combat = is_in_combat(session)

        from mechanics.system.phone import scenario_has_smartphone, get_phone_branding, build_phone_home_embed, PhoneMainView
        if scenario_has_smartphone(scen_key) and not in_combat:
            branding = get_phone_branding(scen_key)
            phone_btn = discord.ui.Button(label=branding["device_name"].split(" ", 1)[-1], emoji=branding["emoji"], style=discord.ButtonStyle.secondary)
            phone_btn.callback = self._phone_callback
            self.add_item(phone_btn)

        if is_location_engine_enabled(scen_key) and not in_combat:
            move_button = discord.ui.Button(label="Move Location", style=discord.ButtonStyle.secondary, emoji="📍")
            move_button.callback = self._move_location_callback
            self.add_item(move_button)

        from scenario_data import is_mechanic_enabled
        party_npcs = session.get("party_npcs") or []
        if party_npcs and not in_combat:
            btn_lbl = "Party" if is_mechanic_enabled(scen_key, "tactical_combat") else "Companions"
            party_btn = discord.ui.Button(label=btn_lbl, style=discord.ButtonStyle.secondary, emoji="💬")
            party_btn.callback = self._party_dialogue_callback
            self.add_item(party_btn)

        current_loc = session.get("current_location", "") if session else ""
        is_hub = is_hub_location(current_loc)

        from mechanics.world.locations import location_has_bounty_board, get_notice_board_label
        if location_has_bounty_board(current_loc, scen_key=scen_key) and not in_combat:
            nb_label, nb_emoji = get_notice_board_label(scen_key)
            notice_button = discord.ui.Button(label=nb_label, style=discord.ButtonStyle.secondary, emoji=nb_emoji)
            notice_button.callback = self._notice_board_callback
            self.add_item(notice_button)

        from mechanics.world.locations import location_has_merchant_shop, is_school_scenario
        is_school = is_school_scenario(scen_key)
        show_merchant = False
        merchant_label = "Talk to Merchant"
        if is_school:
            if location_has_merchant_shop(current_loc, scen_key=scen_key):
                show_merchant = True
                merchant_label = "Visit Shop / Café"
        else:
            has_shop = location_has_merchant_shop(current_loc, scen_key=scen_key)
            if self.merchant.get("available") or has_shop:
                show_merchant = True
                merchant_label = "Visit Market / Shop" if has_shop else "Talk to Merchant"

        if show_merchant and not in_combat:
            merchant_button = discord.ui.Button(label=merchant_label,
                                                 style=discord.ButtonStyle.success, emoji="🛍️")
            merchant_button.callback = self._talk_to_merchant
            self.add_item(merchant_button)

        faction = db.get_faction_by_hq(session_id, current_loc)
        if faction and not in_combat:
            hq_button = discord.ui.Button(label=f"Enter {faction.get('name', 'HQ')}", style=discord.ButtonStyle.primary, emoji="🏛️")
            hq_button.callback = self._faction_hq_callback
            self.add_item(hq_button)

        # Dynamic Conversant Profile Shortcut Button
        from scenario_data import is_mechanic_enabled
        if not in_combat and (is_mechanic_enabled(scen_key, "contact_list") or is_mechanic_enabled(scen_key, "relationship_meter")):
            from mechanics.world.mobility import get_session_dialogue_partners
            dialogue_partners = get_session_dialogue_partners(session)
            if dialogue_partners:
                contacts = db.get_contacts(session_id)
                matching_contacts = []
                for dp in dialogue_partners:
                    for c in contacts:
                        if is_matching_contact_dialogue_partner(c, dp):
                            if not any(mc.get("name") == c.get("name") for mc in matching_contacts):
                                matching_contacts.append(c)
                for contact in matching_contacts:
                    c_name = str(contact.get("name") or "Contact").strip()
                    first_name = c_name.split()[0] if c_name else "Contact"
                    label_name = first_name if len(c_name) > 15 else c_name
                    profile_btn = discord.ui.Button(
                        label=f"Profile: {label_name}"[:80],
                        style=discord.ButtonStyle.secondary,
                        emoji="👤"
                    )
                    profile_btn.callback = self._make_contact_profile_callback(contact)
                    self.add_item(profile_btn)


    async def _phone_callback(self, interaction: discord.Interaction):
        if interaction.user.id not in self.member_ids:
            msg = "You're not part of this adventure."
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
            return
        from mechanics.system.phone import build_phone_home_embed, PhoneMainView
        embed = build_phone_home_embed(self.session_id, interaction.user.id)
        view = PhoneMainView(self.cog, self.session_id, interaction.user.id)
        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        except discord.HTTPException as e:
            if getattr(e, "code", None) == 40060:
                await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            else:
                raise

    def _make_contact_profile_callback(self, contact: dict):
        async def _profile_callback(interaction: discord.Interaction):
            if interaction.user.id not in self.member_ids:
                msg = "You're not part of this adventure."
                if interaction.response.is_done():
                    await interaction.followup.send(msg, ephemeral=True)
                else:
                    await interaction.response.send_message(msg, ephemeral=True)
                return
            from cogs.contacts import build_contact_detail_embed, ContactView
            session = db.get_session(self.session_id) or {}
            scen_key = session.get("scenario", "fantasy")
            embed = build_contact_detail_embed(contact, scen_key, user_id=interaction.user.id)
            char = db.get_character(interaction.user.id)
            char_id = char.get("id", 0) if char else 0
            contacts = db.get_contacts(self.session_id, character_id=char_id)
            view = ContactView(
                contacts, scen_key, interaction.user.id,
                active_contact=contact,
                session_id=self.session_id, cog=self.cog
            )
            try:
                if interaction.response.is_done():
                    await interaction.followup.send(embed=embed, view=view, ephemeral=True)
                else:
                    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            except discord.HTTPException as e:
                if getattr(e, "code", None) == 40060:
                    await interaction.followup.send(embed=embed, view=view, ephemeral=True)
                else:
                    raise
        return _profile_callback


    async def _move_location_callback(self, interaction: discord.Interaction):
        if interaction.user.id not in self.member_ids:
            msg = "You're not part of this adventure."
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
            return

        # Defer immediately to avoid Discord's 3-second interaction timeout & race conditions
        if not interaction.response.is_done():
            try:
                await interaction.response.defer(ephemeral=True)
            except (discord.HTTPException, discord.NotFound):
                pass

        session = db.get_session(self.session_id)
        from mechanics.combat import is_in_combat
        if is_in_combat(session):
            msg = "❌ **Cannot travel while engaged in combat!** Defeat your enemies or flee first."
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
            return
        scen_key = session.get("scenario", "fantasy") if session else "fantasy"
        cur_loc = session.get("current_location", "")
        char = db.get_character(interaction.user.id)
        char_name = char.get("name", "") if char else ""

        from mechanics.world.locations import parse_tiered_location, get_zone_summary_tree, process_llm_location_update, sanitize_location_target
        # Auto-discover any active quest target locations
        active_wps = db.get_all_session_active_waypoints(self.session_id)
        for wp in active_wps:
            target_loc = wp.get("target_location", "").strip()
            if target_loc:
                clean_target = sanitize_location_target(target_loc, session_id=self.session_id, scen_key=scen_key, char_name=char_name)
                process_llm_location_update(self.session_id, clean_target, scen_key, char_name=char_name)

        curr_z, _, _ = parse_tiered_location(cur_loc, scen_key, session_id=self.session_id, char_name=char_name)
        zones_summary = get_zone_summary_tree(self.session_id, scen_key, current_loc=cur_loc, char_name=char_name)
        
        # Directly open the regional places view for the player's current zone
        embed = build_zone_places_embed(self.session_id, curr_z, scen_key, current_loc=cur_loc, char_name=char_name)
        view = PrimarySelectView(self.cog, self.session_id, scen_key, zone_name=curr_z, zones_summary=zones_summary, current_loc=cur_loc, char_name=char_name, sync=True)
        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        except discord.HTTPException as e:
            if getattr(e, "code", None) == 40060:
                await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            else:
                raise

    async def _notice_board_callback(self, interaction: discord.Interaction):
        session = db.get_session(self.session_id)
        if not session:
            await interaction.response.send_message("Session not found.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        bounties = await game_engine.generate_bounty_board(session)
        embed = _build_bounty_board_embed(session, bounties)
        view = BountyBoardView(session, bounties)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    async def _party_dialogue_callback(self, interaction: discord.Interaction):
        party_npcs = db.get_session_party_npcs(self.session_id)
        if not party_npcs:
            await interaction.response.send_message("You have no companions in your party.", ephemeral=True)
            return
        embed = discord.Embed(
            title="🤝 Party Companions",
            description="Select a companion to speak with or manage:",
            color=discord.Color.teal()
        )
        view = PartyDialogueSelectView(self.cog, self.session_id, interaction.user.id, sync=True)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    def _make_callback(self, idx: int):
        async def callback(interaction: discord.Interaction):
            await self.cog.handle_sync_pick(interaction, self.session_id, choice_index=idx)
        return callback

    async def _custom_callback(self, interaction: discord.Interaction):
        if interaction.user.id not in self.member_ids:
            await interaction.response.send_message("You're not part of this adventure.", ephemeral=True)
            return
        session = db.get_session(self.session_id)
        if str(interaction.user.id) in session["pending_picks"]:
            await interaction.response.send_message("You've already locked in your action this round.",
                                                      ephemeral=True)
            return
        await interaction.response.send_modal(CustomActionModal(self.cog, self.session_id, sync=True))

    async def _use_item_callback(self, interaction: discord.Interaction):
        if interaction.user.id not in self.member_ids:
            await interaction.response.send_message("You're not part of this adventure.", ephemeral=True)
            return
        session = db.get_session(self.session_id)
        if str(interaction.user.id) in session["pending_picks"]:
            await interaction.response.send_message("You've already locked in your action this round.", ephemeral=True)
            return
        inv = db.get_inventory(interaction.user.id)
        carried = [i for i in inv if not i.get("equipped")]
        if not carried:
            await interaction.response.send_message("❌ You have no carried items in your inventory.", ephemeral=True)
            return
        view = SceneItemSelectView(self.cog, self.session_id, interaction.user.id, carried, sync=True)
        await interaction.response.send_message("🎒 Select an item from your bag to use:", view=view, ephemeral=True)

    async def _retry_callback(self, interaction: discord.Interaction):
        if interaction.user.id not in self.member_ids:
            await interaction.response.send_message("You're not part of this adventure.", ephemeral=True)
            return
        await self.cog.handle_retry(interaction, self.session_id)

    async def _talk_to_merchant(self, interaction: discord.Interaction):
        # Deliberately does not check/consume pending_picks -- Task 3 treats
        # this as an orthogonal side-channel to the normal pick flow (see
        # _handle_talk_to_merchant's docstring).
        await _handle_talk_to_merchant(self.cog, self.session_id, interaction)

    async def _faction_hq_callback(self, interaction: discord.Interaction):
        if interaction.user.id not in self.member_ids:
            await interaction.response.send_message("You're not part of this adventure.", ephemeral=True)
            return
        await self.cog.open_faction_hq_menu(interaction, self.session_id, interaction.user.id)


from .quests import BountyBoardView
from .social import PartyDialogueSelectView
from .locations import PrimarySelectView, SceneItemSelectView
