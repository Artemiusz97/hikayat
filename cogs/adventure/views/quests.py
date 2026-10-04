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

class ActiveBountySelect(discord.ui.Select):
    def __init__(self, session_id: int, bounties: list[dict], selected_quest_id: str | None = None):
        options = [
            discord.SelectOption(
                label="🔍 Overview (All Active Bounties)",
                value="__overview__",
                description="View compact summary of all active bounties",
                emoji="📋",
                default=(selected_quest_id is None)
            )
        ]
        for b in bounties[:24]:
            qid = str(b.get("quest_id", ""))
            lbl = b.get("title", "Bounty")[:100]
            obj = b.get("objective", "")[:90]
            icon = _quest_type_icon(b.get("quest_type", ""))
            options.append(discord.SelectOption(
                label=lbl,
                value=qid,
                description=obj,
                emoji=icon,
                default=(selected_quest_id == qid)
            ))
        super().__init__(placeholder="Select an active bounty to inspect details...", min_values=1, max_values=1, options=options, row=1)
        self.session_id = session_id

    async def callback(self, interaction: discord.Interaction):
        val = self.values[0]
        selected_id = None if val == "__overview__" else val
        view = QuestLogView(self.session_id, current_tab="Bounties", selected_quest_id=selected_id)
        embed = _build_quest_log_embed(self.session_id, tab="Bounties", selected_quest_id=selected_id)
        await interaction.response.edit_message(embed=embed, view=view)

class HistoryQuestSelect(discord.ui.Select):
    def __init__(self, session_id: int, history_quests: list[dict], selected_quest_id: str | None = None):
        options = [
            discord.SelectOption(
                label="📜 Overview (History Summary)",
                value="__overview__",
                description="View career record and all archived quests",
                emoji="📊",
                default=(selected_quest_id is None)
            )
        ]
        for q in history_quests[:24]:
            qid = str(q.get("quest_id", ""))
            lbl = q.get("title", "Past Quest")[:100]
            status = q.get("status", "Completed")
            status_icon = "✅" if status == "Completed" else "🛑"
            desc = f"{status} • {q.get('objective', '')[:75]}"[:100]
            options.append(discord.SelectOption(
                label=lbl,
                value=qid,
                description=desc,
                emoji=status_icon,
                default=(selected_quest_id == qid)
            ))
        super().__init__(placeholder="Select a past quest to inspect dossier...", min_values=1, max_values=1, options=options, row=1)
        self.session_id = session_id

    async def callback(self, interaction: discord.Interaction):
        val = self.values[0]
        selected_id = None if val == "__overview__" else val
        view = QuestLogView(self.session_id, current_tab="History", selected_quest_id=selected_id)
        embed = _build_quest_log_embed(self.session_id, tab="History", selected_quest_id=selected_id)
        await interaction.response.edit_message(embed=embed, view=view)

class CaseboardSuspectSelect(discord.ui.Select):
    def __init__(self, session_id: int, suspects: list[str], selected_suspect: str | None = None):
        options = [
            discord.SelectOption(
                label="🔍 All Evidence & Leads",
                value="__all__",
                description="View complete campaign evidence archive",
                emoji="🗂️",
                default=(selected_suspect in (None, "__all__", ""))
            )
        ]
        for s in suspects[:24]:
            options.append(discord.SelectOption(
                label=s[:100],
                value=s,
                description=f"Evidence and testimony implicating {s}"[:100],
                emoji="👤",
                default=(selected_suspect == s)
            ))
        super().__init__(placeholder="Filter caseboard by linked suspect...", min_values=1, max_values=1, options=options, row=1)
        self.session_id = session_id

    async def callback(self, interaction: discord.Interaction):
        val = self.values[0]
        selected_suspect = None if val == "__all__" else val
        view = QuestLogView(self.session_id, current_tab="Caseboard", selected_suspect=selected_suspect)
        embed = _build_quest_log_embed(self.session_id, tab="Caseboard", selected_suspect=selected_suspect)
        await interaction.response.edit_message(embed=embed, view=view)

class ClueDeductionView(discord.ui.View):
    def __init__(self, session_id: int, all_clues: list[dict]):
        super().__init__(timeout=180)
        self.session_id = session_id
        # Filter available: only unconsumed leads and not already a breakthrough deduction
        self.all_clues = [c for c in all_clues if not c.get("is_consumed") and c.get("category") != "deduction"]
        self.clue_a_id = None
        self.clue_b_id = None

        options_a = []
        options_b = []
        for c in self.all_clues[:25]:
            cid = str(c["id"])
            lbl = c["title"][:90]
            cat = c.get("category", "physical")
            cat_icon = "🗣️" if cat == "testimonial" else ("💾" if cat == "digital" else ("📄" if cat == "document" else "🔍"))
            stat_hint = "CHA" if cat == "testimonial" else ("INT" if cat in ("digital", "document") else "PER")
            desc = f"[{stat_hint}] Ch.{c.get('chapter', 1)} • {c.get('source_location', 'Area')}"[:100]
            options_a.append(discord.SelectOption(label=lbl, value=cid, description=desc, emoji=cat_icon))
            options_b.append(discord.SelectOption(label=lbl, value=cid, description=desc, emoji=cat_icon))

        self.select_a = discord.ui.Select(placeholder="Select Primary Evidence A...", min_values=1, max_values=1, options=options_a, row=0)
        self.select_b = discord.ui.Select(placeholder="Select Corroborating Evidence B...", min_values=1, max_values=1, options=options_b, row=1)

        self.select_a.callback = self._on_select_a
        self.select_b.callback = self._on_select_b

        self.add_item(self.select_a)
        self.add_item(self.select_b)

        deduce_btn = discord.ui.Button(label="Deduce Connection", emoji="🧩", style=discord.ButtonStyle.success, row=2)
        deduce_btn.callback = self._on_deduce
        self.add_item(deduce_btn)

        cancel_btn = discord.ui.Button(label="Cancel", emoji="🔙", style=discord.ButtonStyle.secondary, row=2)
        cancel_btn.callback = self._on_cancel
        self.add_item(cancel_btn)

    async def _on_select_a(self, interaction: discord.Interaction):
        self.clue_a_id = int(self.select_a.values[0])
        await interaction.response.defer()

    async def _on_select_b(self, interaction: discord.Interaction):
        self.clue_b_id = int(self.select_b.values[0])
        await interaction.response.defer()

    async def _on_cancel(self, interaction: discord.Interaction):
        view = QuestLogView(self.session_id, current_tab="Caseboard")
        embed = _build_quest_log_embed(self.session_id, tab="Caseboard")
        await interaction.response.edit_message(embed=embed, view=view)

    async def _on_deduce(self, interaction: discord.Interaction):
        if not self.clue_a_id or not self.clue_b_id:
            await interaction.response.send_message("Please select both Evidence A and Evidence B first!", ephemeral=True)
            return
        if self.clue_a_id == self.clue_b_id:
            await interaction.response.send_message("Please select two distinct pieces of evidence to deduce a connection.", ephemeral=True)
            return

        clue_a = db.get_session_clue_by_id(self.clue_a_id)
        clue_b = db.get_session_clue_by_id(self.clue_b_id)
        if not clue_a or not clue_b:
            await interaction.response.send_message("One or both evidence items could not be found.", ephemeral=True)
            return

        if clue_a.get("is_consumed") or clue_b.get("is_consumed"):
            await interaction.response.send_message("One or both leads have already been consumed in a previous breakthrough!", ephemeral=True)
            return

        from mechanics.narrative.clues import evaluate_clue_deduction
        session = db.get_session(self.session_id)
        scen_key = session.get("scenario", "fantasy") if session else "fantasy"
        is_valid, title, detail_text = evaluate_clue_deduction(clue_a, clue_b, scen_key=scen_key)

        if not is_valid:
            await interaction.response.send_message(f"🔍 **No Connection Found:** {detail_text}", ephemeral=True)
            return

        # S.P.E.C.I.A.L. Stat Check
        char_row = db.get_character(interaction.user.id) or {}
        cats = {clue_a.get("category", "physical"), clue_b.get("category", "physical")}
        if "deduction" in cats or "digital" in cats or "document" in cats:
            stat_key = "int_"
            stat_name = "INT"
        elif "testimonial" in cats:
            stat_key = "cha"
            stat_name = "CHA"
        else:
            stat_key = "per_"
            stat_name = "PER"

        stat_val = char_row.get(stat_key, 5) if char_row else 5
        success_rate = max(10, min(100, 20 + (stat_val * 10)))

        import random
        roll = random.randint(1, 100)
        if roll > success_rate:
            await interaction.response.send_message(
                f"🎲 **Deduction Check Failed!** (Rolled `{roll}` vs `{success_rate}%` {stat_name})\n\n"
                f"You tried to connect the evidence, but couldn't quite see the full picture.\n"
                f"*Leads are NOT consumed.* Boost your **{stat_name}** or try again later!",
                ephemeral=True
            )
            return

        cur_ch = db.get_session_chapter(self.session_id) or 1
        db.synthesize_deduction_clue(self.session_id, [self.clue_a_id, self.clue_b_id], title, detail_text, chapter=cur_ch)
        members = db.get_session_members(self.session_id)
        for uid in members:
            try:
                db.add_xp(uid, 50)
            except Exception:
                pass

        embed = discord.Embed(
            title=f"⚡ Deduction Breakthrough: {title}!",
            description=(
                f"🎲 **Success Check:** Rolled `{roll}` vs `{success_rate}%` ({stat_name})\n\n"
                f"{detail_text}\n\n"
                f"🎉 **Reward:** `+50 XP` awarded to party!\n"
                f"Both component leads have been verified and archived. Confrontation choices unlocked in story scenes!"
            ),
            color=discord.Color.gold()
        )
        view = QuestLogView(self.session_id, current_tab="Caseboard")
        await interaction.response.edit_message(embed=embed, view=view)

class QuestLogView(discord.ui.View):
    def __init__(self, session_id: int, current_tab: str = "Main Quest", selected_quest_id: str | None = None, selected_suspect: str | None = None):
        super().__init__(timeout=300)
        self.session_id = session_id
        self.current_tab = "Main Quest" if current_tab in ("Active", "Notes") else current_tab
        self.selected_quest_id = selected_quest_id
        self.selected_suspect = selected_suspect

        session = db.get_session(session_id)
        scen_key = session.get("scenario", "fantasy") if session else "fantasy"
        cur_loc = session.get("current_location", "") if session else ""
        labels = _get_quest_scenario_labels(scen_key)

        main_btn = discord.ui.Button(
            label=labels["main_tab"],
            emoji=labels["main_emoji"],
            style=discord.ButtonStyle.primary if self.current_tab == "Main Quest" else discord.ButtonStyle.secondary,
            row=0
        )
        bounties_btn = discord.ui.Button(
            label=labels["bounties_tab"],
            emoji=labels["bounties_emoji"],
            style=discord.ButtonStyle.primary if self.current_tab == "Bounties" else discord.ButtonStyle.secondary,
            row=0
        )
        goals_btn = discord.ui.Button(
            label="Campaign Goals",
            emoji="🏆",
            style=discord.ButtonStyle.primary if self.current_tab == "Goals" else discord.ButtonStyle.secondary,
            row=0
        )
        caseboard_btn = discord.ui.Button(
            label="Caseboard",
            emoji="🗂️",
            style=discord.ButtonStyle.primary if self.current_tab == "Caseboard" else discord.ButtonStyle.secondary,
            row=0
        )
        history_btn = discord.ui.Button(
            label="History",
            emoji="📜",
            style=discord.ButtonStyle.primary if self.current_tab == "History" else discord.ButtonStyle.secondary,
            row=0
        )

        main_btn.callback = self._make_tab_callback("Main Quest")
        bounties_btn.callback = self._make_tab_callback("Bounties")
        goals_btn.callback = self._make_tab_callback("Goals")
        caseboard_btn.callback = self._make_tab_callback("Caseboard")
        history_btn.callback = self._make_tab_callback("History")

        self.add_item(main_btn)
        self.add_item(bounties_btn)
        self.add_item(goals_btn)
        self.add_item(caseboard_btn)
        self.add_item(history_btn)

        # Conditionally render Notice Board button ONLY if location has a board and tab supports it
        from mechanics.world.locations import location_has_bounty_board
        has_board = location_has_bounty_board(cur_loc, scen_key=scen_key)

        if has_board and self.current_tab == "Main Quest":
            board_btn = discord.ui.Button(
                label=labels["board_label"],
                emoji=labels["board_emoji"],
                style=discord.ButtonStyle.secondary,
                row=1
            )
            board_btn.callback = self._open_bounty_board
            self.add_item(board_btn)

        # Dropdowns and Sub-Actions
        if self.current_tab == "Bounties":
            all_active = db.get_session_quests(session_id, status="Active")
            active_bounties = [
                q for q in all_active
                if not (q.get("is_story_quest") or q.get("quest_type") in ("Story Quest", "Main Quest"))
                and q.get("title") and q["title"] not in ("Active Objective", "Complete objective.", "")
            ]
            seen = set()
            deduped = []
            for b in active_bounties:
                qid = b.get("quest_id") or b.get("title")
                if qid not in seen:
                    seen.add(qid)
                    deduped.append(b)
            if deduped:
                self.add_item(ActiveBountySelect(session_id, deduped, selected_quest_id=selected_quest_id))

            if has_board:
                board_btn = discord.ui.Button(
                    label=labels["board_label"],
                    emoji=labels["board_emoji"],
                    style=discord.ButtonStyle.secondary,
                    row=2
                )
                board_btn.callback = self._open_bounty_board
                self.add_item(board_btn)

            if selected_quest_id:
                back_btn = discord.ui.Button(label="All Bounties", emoji="⬅️", style=discord.ButtonStyle.secondary, row=2)
                back_btn.callback = self._back_to_bounties_overview
                self.add_item(back_btn)

                abandon_btn = discord.ui.Button(label="Abandon Bounty", emoji="❌", style=discord.ButtonStyle.danger, row=2)
                abandon_btn.callback = self._abandon_selected_bounty
                self.add_item(abandon_btn)

        elif self.current_tab == "Caseboard":
            all_clues = db.get_session_clues(session_id)
            if not all_clues:
                all_clues = db.get_session_clues(session_id)

            suspects = sorted(list({c["linked_npc"].strip() for c in all_clues if c.get("linked_npc") and c["linked_npc"].strip()}))
            if suspects:
                self.add_item(CaseboardSuspectSelect(session_id, suspects, selected_suspect=self.selected_suspect))

            available = [c for c in all_clues if not c.get("is_consumed") and c.get("category") != "deduction"]
            if len(available) >= 2:
                deduce_btn = discord.ui.Button(label="Connect 2 Leads", emoji="🧩", style=discord.ButtonStyle.primary, row=2)
                deduce_btn.callback = self._open_deduction_menu
                self.add_item(deduce_btn)

        elif self.current_tab == "History":
            all_quests = db.get_session_quests(session_id)
            history_quests = [
                q for q in all_quests
                if q.get("status") in ("Completed", "Failed", "Abandoned")
                and q.get("title") and q["title"] not in ("Active Objective", "Complete objective.", "")
            ]
            seen = set()
            deduped = []
            for q in history_quests:
                qid = q.get("quest_id") or q.get("title")
                if qid not in seen:
                    seen.add(qid)
                    deduped.append(q)
            if deduped:
                self.add_item(HistoryQuestSelect(session_id, deduped, selected_quest_id=selected_quest_id))

            if selected_quest_id:
                back_hist_btn = discord.ui.Button(label="All History", emoji="⬅️", style=discord.ButtonStyle.secondary, row=2)
                back_hist_btn.callback = self._back_to_history_overview
                self.add_item(back_hist_btn)

    def _make_tab_callback(self, tab: str):
        async def callback(interaction: discord.Interaction):
            view = QuestLogView(self.session_id, current_tab=tab, selected_quest_id=None, selected_suspect=None)
            embed = _build_quest_log_embed(self.session_id, tab=tab, selected_quest_id=None, selected_suspect=None)
            await interaction.response.edit_message(embed=embed, view=view)
        return callback

    async def _open_deduction_menu(self, interaction: discord.Interaction):
        all_clues = db.get_session_clues(self.session_id)
        available = [c for c in all_clues if not c.get("is_consumed") and c.get("category") != "deduction"]
        if len(available) < 2:
            await interaction.response.send_message("You need at least 2 unconsumed pieces of evidence to deduce a connection.", ephemeral=True)
            return
        view = ClueDeductionView(self.session_id, available)
        embed = discord.Embed(
            title="🧩 Deduction & Evidence Pairing",
            description="Select two unconsumed leads from your case file to cross-reference their details and attempt a S.P.E.C.I.A.L. Breakthrough check!",
            color=discord.Color.purple()
        )
        await interaction.response.edit_message(embed=embed, view=view)

    async def _back_to_bounties_overview(self, interaction: discord.Interaction):
        view = QuestLogView(self.session_id, current_tab="Bounties", selected_quest_id=None)
        embed = _build_quest_log_embed(self.session_id, tab="Bounties", selected_quest_id=None)
        await interaction.response.edit_message(embed=embed, view=view)

    async def _back_to_history_overview(self, interaction: discord.Interaction):
        view = QuestLogView(self.session_id, current_tab="History", selected_quest_id=None)
        embed = _build_quest_log_embed(self.session_id, tab="History", selected_quest_id=None)
        await interaction.response.edit_message(embed=embed, view=view)

    async def _abandon_selected_bounty(self, interaction: discord.Interaction):
        if not self.selected_quest_id:
            await interaction.response.send_message("No bounty selected to abandon.", ephemeral=True)
            return
        bounty = db.get_quest_by_id(self.session_id, self.selected_quest_id)
        if not bounty:
            await interaction.response.send_message("Bounty not found.", ephemeral=True)
            return
        db.update_quest_status(self.session_id, self.selected_quest_id, "Abandoned")
        view = QuestLogView(self.session_id, current_tab="Bounties", selected_quest_id=None)
        embed = _build_quest_log_embed(self.session_id, tab="Bounties", selected_quest_id=None)
        await interaction.response.edit_message(embed=embed, view=view)
        await interaction.followup.send(
            f"🗑️ Abandoned bounty: **{bounty.get('title', 'Bounty')}**.\nThe bounty slot is now freed up!",
            ephemeral=True
        )

    async def _open_bounty_board(self, interaction: discord.Interaction):
        session = db.get_session(self.session_id)
        if not session:
            await interaction.response.send_message("Session not found.", ephemeral=True)
            return
        current_loc = session.get("current_location", "")
        scen_key = session.get("scenario", "fantasy")
        from mechanics.world.locations import location_has_bounty_board, get_notice_board_label
        if not location_has_bounty_board(current_loc, scen_key=scen_key):
            nb_label, nb_emoji = get_notice_board_label(scen_key)
            await interaction.response.send_message(
                f"{nb_emoji} **No {nb_label} Here!**\n"
                f"You are currently at **{current_loc or 'an unknown location'}**.\n"
                f"Use **📍 Move Location** to visit a local Guild Hall, Campus Bulletin, Tavern, or Hub to accept new side bounties.",
                ephemeral=True
            )
            return
        await interaction.response.defer()
        bounties = await game_engine.generate_bounty_board(session)
        embed = _build_bounty_board_embed(session, bounties)
        view = BountyBoardView(session, bounties)
        await interaction.followup.edit_message(message_id=interaction.message.id, embed=embed, view=view)

class BountySelect(discord.ui.Select):
    def __init__(self, session_id: int, bounties: list[dict]):
        options = []
        for b in bounties[:25]:
            label = b["title"][:100]
            item_note = f", Item: {b['reward_item']}" if b.get("reward_item") else ""
            desc = f"Reward: {b.get('reward_xp', 150)}XP, {b.get('reward_gold', 40)}G{item_note}"[:100]
            icon = _quest_type_icon(b.get("quest_type", ""))
            options.append(discord.SelectOption(
                label=label,
                value=b["quest_id"],
                description=desc,
                emoji=icon
            ))
        super().__init__(placeholder="Select a bounty to accept...", min_values=1, max_values=1, options=options)
        self.session_id = session_id

    async def callback(self, interaction: discord.Interaction):
        quest_id = self.values[0]
        quest = db.get_quest_by_id(self.session_id, quest_id)
        if not quest or quest.get("status") != "Available":
            await interaction.response.send_message("That bounty is no longer available.", ephemeral=True)
            return

        db.update_quest_status(self.session_id, quest_id, "Active")

        session = db.get_session(self.session_id)
        remaining_bounties = db.get_session_quests(self.session_id, status="Available")
        embed = _build_bounty_board_embed(session, remaining_bounties)
        view = BountyBoardView(session, remaining_bounties)

        await interaction.response.edit_message(embed=embed, view=view)
        await interaction.followup.send(
            f"🎯 **Bounty Accepted!** Added **{quest['title']}** to your active Quest Log.\n"
            f"Objective: {quest['objective']}",
            ephemeral=True
        )

class BountyBoardView(discord.ui.View):
    def __init__(self, session: dict, bounties: list[dict]):
        super().__init__(timeout=300)
        self.session = session
        self.session_id = session["id"]

        if bounties:
            self.add_item(BountySelect(self.session_id, bounties))

        refresh_btn = discord.ui.Button(label="Refresh Board", emoji="🔄", style=discord.ButtonStyle.primary)
        quest_btn = discord.ui.Button(label="Quest Log", emoji="📜", style=discord.ButtonStyle.secondary)

        refresh_btn.callback = self._refresh_board
        quest_btn.callback = self._open_quest_log

        self.add_item(refresh_btn)
        self.add_item(quest_btn)

    async def _refresh_board(self, interaction: discord.Interaction):
        await interaction.response.defer()
        new_bounties = await game_engine.generate_bounty_board(self.session, force_refresh=True)
        embed = _build_bounty_board_embed(self.session, new_bounties)
        view = BountyBoardView(self.session, new_bounties)
        await interaction.followup.edit_message(message_id=interaction.message.id, embed=embed, view=view)

    async def _open_quest_log(self, interaction: discord.Interaction):
        embed = _build_quest_log_embed(self.session_id, tab="Main Quest")
        view = QuestLogView(self.session_id, current_tab="Main Quest")
        await interaction.response.edit_message(embed=embed, view=view)

