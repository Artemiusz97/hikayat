from __future__ import annotations
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
        view, embed = await create_quest_log_view_and_embed(self.session_id, tab="Bounties", selected_quest_id=selected_id)
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
        view, embed = await create_quest_log_view_and_embed(self.session_id, tab="History", selected_quest_id=selected_id)
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
        view, embed = await create_quest_log_view_and_embed(self.session_id, tab="Caseboard", selected_suspect=selected_suspect)
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
        for opt in self.select_a.options:
            opt.default = (opt.value == self.select_a.values[0])
        await interaction.response.edit_message(view=self)

    async def _on_select_b(self, interaction: discord.Interaction):
        self.clue_b_id = int(self.select_b.values[0])
        for opt in self.select_b.options:
            opt.default = (opt.value == self.select_b.values[0])
        await interaction.response.edit_message(view=self)

    async def _on_cancel(self, interaction: discord.Interaction):
        view, embed = await create_quest_log_view_and_embed(self.session_id, tab="Caseboard")
        await interaction.response.edit_message(embed=embed, view=view)

    async def _on_deduce(self, interaction: discord.Interaction):
        if not self.clue_a_id:
            await interaction.response.send_message("Please select at least Evidence A first!", ephemeral=True)
            return

        is_single = not self.clue_b_id or int(self.clue_a_id) == int(self.clue_b_id)

        clue_a = await adb(db.get_session_clue_by_id, self.clue_a_id)
        if not clue_a:
            await interaction.response.send_message("Evidence A could not be found.", ephemeral=True)
            return
        if clue_a.get("is_consumed"):
            await interaction.response.send_message("Evidence A has already been consumed in a previous breakthrough!", ephemeral=True)
            return

        if is_single:
            pair_key = f"single:{int(self.clue_a_id)}"
            eff_clue_b_id = None
        else:
            clue_b = await adb(db.get_session_clue_by_id, self.clue_b_id)
            if not clue_b:
                await interaction.response.send_message("Evidence B could not be found.", ephemeral=True)
                return
            if clue_b.get("is_consumed"):
                await interaction.response.send_message("Evidence B has already been consumed in a previous breakthrough!", ephemeral=True)
                return
            pair_key = f"{min(int(self.clue_a_id), int(self.clue_b_id))}:{max(int(self.clue_a_id), int(self.clue_b_id))}"
            eff_clue_b_id = self.clue_b_id

        session = await adb(db.get_session, self.session_id)
        cur_turn = len((session or {}).get("history") or [])
        attempts_map = dict((session or {}).get("deduction_attempts_turn") or {})
        if attempts_map.get(pair_key) == cur_turn:
            await interaction.response.send_message("⏳ You already attempted to connect this lead or pair this turn. Advance the story or try another lead!", ephemeral=True)
            return

        ded_res = await adb(
            game_engine.resolve_caseboard_deduction,
            self.session_id,
            self.clue_a_id,
            eff_clue_b_id,
            interaction.user.id,
        )
        attempts_map[pair_key] = cur_turn
        await adb(db.update_session, self.session_id, extra={"deduction_attempts_turn": attempts_map})

        if not ded_res.get("is_valid"):
            prefix = "🚩 **Red Herring Rejected:**" if ded_res.get("is_red_herring") else "🔍 **No Logical Link:**"
            await interaction.response.send_message(
                f"{prefix} {ded_res.get('detail_text') or 'These two items do not corroborate a shared lead.'}",
                ephemeral=True,
            )
            return

        title = ded_res.get("title") or "Confirmed Trail"
        detail_text = ded_res.get("detail_text") or ""
        unlock_notes = []
        if ded_res.get("climax_unlocked"):
            unlock_notes.append("🔓 **Climax Unlocked:** Hidden culprit / lair revealed!")
        if ded_res.get("twist_revealed"):
            unlock_notes.append("⚡ **Twist Uncovered:** New side-switch / blackmail leverage unlocked!")
        extra_str = ("\n" + "\n".join(unlock_notes)) if unlock_notes else ""

        embed = discord.Embed(
            title=f"⚡ Deduction Breakthrough: {title}!",
            description=(
                f"🧩 **Corroborated Logic Link Verified**\n\n"
                f"{detail_text}\n\n"
                f"🎉 **Reward:** `+{ded_res.get('xp_awarded', 50)} XP` awarded to party!{extra_str}"
            ),
            color=discord.Color.gold()
        )
        view, _ = await create_quest_log_view_and_embed(self.session_id, tab="Caseboard", custom_embed=embed)
        await interaction.response.edit_message(embed=embed, view=view)


def _hydrate_quest_log_data(
    session_id: int,
    current_tab: str = "Main Quest",
    selected_quest_id: str | None = None,
    selected_suspect: str | None = None,
) -> dict:
    norm_tab = "Main Quest" if current_tab in ("Active", "Notes") else current_tab
    session = db.get_session(session_id) or {}
    scen_key = session.get("scenario", "fantasy") if session else "fantasy"
    cur_loc = session.get("current_location", "") if session else ""
    data = {
        "session": session,
        "scen_key": scen_key,
        "cur_loc": cur_loc,
        "active_bounties": [],
        "dossier": None,
        "clues": [],
        "compiled_dossiers": [],
        "history_quests": [],
    }
    if norm_tab == "Bounties":
        all_active = db.get_session_quests(session_id, status="Active") or []
        data["active_bounties"] = [
            q for q in all_active
            if not (q.get("is_story_quest") or q.get("quest_type") in ("Story Quest", "Main Quest"))
            and q.get("title") and q["title"] not in ("Active Objective", "Complete objective.", "")
        ]
        if selected_quest_id:
            data["dossier"] = db.get_quest_dossier(session_id, selected_quest_id)
    elif norm_tab == "Caseboard":
        data["clues"] = db.get_session_clues(session_id) or []
        data["compiled_dossiers"] = db.get_session_quest_dossiers(session_id, status_stage="compiled") or []
    elif norm_tab == "History":
        all_quests = db.get_session_quests(session_id) or []
        data["history_quests"] = [
            q for q in all_quests
            if q.get("status") in ("Completed", "Failed", "Abandoned")
            and q.get("title") and q["title"] not in ("Active Objective", "Complete objective.", "")
        ]
    return data


async def create_quest_log_view_and_embed(
    session_id: int,
    tab: str = "Main Quest",
    selected_quest_id: str | None = None,
    selected_suspect: str | None = None,
    custom_embed: discord.Embed | None = None,
) -> tuple[QuestLogView, discord.Embed]:
    hydrated = await adb(_hydrate_quest_log_data, session_id, tab, selected_quest_id, selected_suspect)
    embed = custom_embed if custom_embed is not None else await adb(
        _build_quest_log_embed,
        session_id,
        tab=tab,
        selected_quest_id=selected_quest_id,
        selected_suspect=selected_suspect,
    )
    view = QuestLogView(
        session_id,
        current_tab=tab,
        selected_quest_id=selected_quest_id,
        selected_suspect=selected_suspect,
        hydrated=hydrated,
    )
    return view, embed


class QuestLogView(discord.ui.View):
    def __init__(
        self,
        session_id: int,
        current_tab: str = "Main Quest",
        selected_quest_id: str | None = None,
        selected_suspect: str | None = None,
        hydrated: dict | None = None,
    ):
        super().__init__(timeout=300)
        self.session_id = session_id
        self.current_tab = "Main Quest" if current_tab in ("Active", "Notes") else current_tab
        self.selected_quest_id = selected_quest_id
        self.selected_suspect = selected_suspect
        self.hydrated = hydrated

        if hydrated is not None:
            session = hydrated.get("session") or {}
            scen_key = hydrated.get("scen_key") or (session.get("scenario", "fantasy") if session else "fantasy")
            cur_loc = hydrated.get("cur_loc") if "cur_loc" in hydrated else (session.get("current_location", "") if session else "")
        else:
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

        world_pulse_btn = discord.ui.Button(label="World Pulse", emoji="🌐", style=discord.ButtonStyle.secondary, row=4)
        world_pulse_btn.callback = self._open_world_pulse
        self.add_item(world_pulse_btn)

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
            if hydrated is not None:
                active_bounties = hydrated.get("active_bounties") or []
            else:
                all_active = db.get_session_quests(session_id, status="Active") or []
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

            if has_board and not selected_quest_id:
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

                dos = hydrated.get("dossier") if hydrated is not None else db.get_quest_dossier(session_id, selected_quest_id)
                if dos and dos.get("status_stage") == "compiled":
                    self.add_item(ContractDispositionSelect(session_id, selected_quest_id, dos, row=3))

        elif self.current_tab == "Caseboard":
            all_clues = (hydrated.get("clues") if hydrated is not None else db.get_session_clues(session_id)) or []
            suspect_set = {c["linked_npc"].strip() for c in all_clues if c.get("linked_npc") and c["linked_npc"].strip()}
            comp_dossiers = (
                hydrated.get("compiled_dossiers")
                if hydrated is not None
                else (db.get_session_quest_dossiers(session_id, status_stage="compiled") or [])
            )
            for dos in (comp_dossiers or []):
                cb = dos.get("cast_bindings") or {}
                climax = dos.get("climax_spec") or {}
                twist = dos.get("twist_spec") or {}
                climax_unlocked = bool(climax.get("gate_type") == "open" or climax.get("is_unlocked"))
                twist_visible = bool(twist.get("has_twist") and twist.get("is_discovered"))
                client_nm = (cb.get("client") or {}).get("name") if isinstance(cb.get("client"), dict) else ""
                if client_nm and str(client_nm).strip():
                    suspect_set.add(str(client_nm).strip())
                for ld in (dos.get("leads_graph") or []):
                    if ld.get("status") in ("unlocked", "active", "completed") or ld.get("roster_cleared") or ld.get("is_discovered"):
                        tgt_npc = ld.get("target_npc")
                        if tgt_npc and str(tgt_npc).strip():
                            suspect_set.add(str(tgt_npc).strip())
                if climax_unlocked or twist_visible:
                    for r_key in ("target", "accomplice", "informant"):
                        nm = (cb.get(r_key) or {}).get("name") if isinstance(cb.get(r_key), dict) else ""
                        if nm and str(nm).strip():
                            suspect_set.add(str(nm).strip())

            suspects = sorted(list(suspect_set))
            if suspects:
                self.add_item(CaseboardSuspectSelect(session_id, suspects, selected_suspect=self.selected_suspect))

            available = [c for c in all_clues if not c.get("is_consumed") and c.get("category") != "deduction"]
            if len(available) >= 1:
                btn_lbl = "Connect 2 Leads" if len(available) >= 2 else "Folklore Deduction"
                deduce_btn = discord.ui.Button(label=btn_lbl, emoji="🧩", style=discord.ButtonStyle.primary, row=2)
                deduce_btn.callback = self._open_deduction_menu
                self.add_item(deduce_btn)

            if self.selected_suspect and self.selected_suspect != "__all__":
                priv_btn = discord.ui.Button(label="Confront Privately", emoji="🗣️", style=discord.ButtonStyle.secondary, row=2)
                priv_btn.callback = self._make_accuse_callback("private")
                self.add_item(priv_btn)

                pub_btn = discord.ui.Button(label="Accuse Publicly", emoji="⚖️", style=discord.ButtonStyle.danger, row=2)
                pub_btn.callback = self._make_accuse_callback("formal")
                self.add_item(pub_btn)

        elif self.current_tab == "History":
            if hydrated is not None:
                history_quests = hydrated.get("history_quests") or []
            else:
                all_quests = db.get_session_quests(session_id) or []
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

    async def _open_world_pulse(self, interaction: discord.Interaction):
        from .world_pulse import WorldPulseView, build_world_pulse_embed
        from mechanics.world.world_events.engine import build_client_world_pulse_payload
        payload = await adb(build_client_world_pulse_payload, self.session_id)
        embed = build_world_pulse_embed(self.session_id, "all", payload=payload)
        uid = interaction.user.id if getattr(interaction, "user", None) else 0
        view = WorldPulseView(self.session_id, uid, filter_mode="all", payload=payload)
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    def _make_tab_callback(self, tab: str):
        async def callback(interaction: discord.Interaction):
            view, embed = await create_quest_log_view_and_embed(self.session_id, tab=tab, selected_quest_id=None, selected_suspect=None)
            await interaction.response.edit_message(embed=embed, view=view)
        return callback

    async def _open_deduction_menu(self, interaction: discord.Interaction):
        all_clues = await adb(db.get_session_clues, self.session_id)
        available = [c for c in all_clues if not c.get("is_consumed") and c.get("category") != "deduction"]
        if not available:
            await interaction.response.send_message("You need at least 1 unconsumed piece of evidence to deduce a connection.", ephemeral=True)
            return
        view = ClueDeductionView(self.session_id, available)
        embed = discord.Embed(
            title="🧩 Deduction & Evidence Pairing",
            description="Select two unconsumed leads from your case file to cross-reference their details and attempt a S.P.E.C.I.A.L. Breakthrough check!",
            color=discord.Color.purple()
        )
        await interaction.response.edit_message(embed=embed, view=view)

    async def _back_to_bounties_overview(self, interaction: discord.Interaction):
        view, embed = await create_quest_log_view_and_embed(self.session_id, tab="Bounties", selected_quest_id=None)
        await interaction.response.edit_message(embed=embed, view=view)

    async def _back_to_history_overview(self, interaction: discord.Interaction):
        view, embed = await create_quest_log_view_and_embed(self.session_id, tab="History", selected_quest_id=None)
        await interaction.response.edit_message(embed=embed, view=view)

    def _make_accuse_callback(self, mode: str):
        async def callback(interaction: discord.Interaction):
            suspect = self.selected_suspect
            if not suspect or suspect == "__all__":
                await interaction.response.send_message("Select a suspect from the Caseboard filter first.", ephemeral=True)
                return
            all_clues = await adb(db.get_session_clues, self.session_id) or []
            suspect_low = suspect.strip().lower()
            clue_qids = {
                str(c["quest_id"])
                for c in all_clues
                if c.get("quest_id") and str(c.get("linked_npc") or "").strip().lower() == suspect_low
            }
            dossiers = await adb(db.get_session_quest_dossiers, self.session_id, "compiled") or []
            target_qid = None
            fallback_qid = None
            for d in dossiers:
                qid = d.get("quest_id")
                q_row = await adb(db.get_quest_by_id, self.session_id, qid)
                if not q_row or q_row.get("status") != "Active":
                    continue
                if not fallback_qid:
                    fallback_qid = qid
                if str(qid) in clue_qids:
                    target_qid = qid
                    break
                cb = d.get("cast_bindings") or {}
                cast_names = [
                    str(((cb.get(r) or {}).get("name") if isinstance(cb.get(r), dict) else "")).strip().lower()
                    for r in ("target", "accomplice", "client", "informant")
                ]
                climax_culprit = str((d.get("climax_spec") or {}).get("true_culprit") or "").strip().lower()
                lead_npcs = [
                    str(ld.get("target_npc") or "").strip().lower()
                    for ld in (d.get("leads_graph") or [])
                    if isinstance(ld, dict)
                ]
                if suspect_low in cast_names or suspect_low == climax_culprit or suspect_low in lead_npcs:
                    target_qid = qid
                    break
            target_qid = target_qid or fallback_qid
            if not target_qid:
                await interaction.response.send_message("No active compiled investigation dossier found.", ephemeral=True)
                return

            res = await adb(
                game_engine.resolve_suspect_accusation,
                self.session_id,
                target_qid,
                suspect,
                mode,
                interaction.user.id,
            )
            view, embed = await create_quest_log_view_and_embed(self.session_id, tab="Caseboard", selected_suspect=suspect)
            await interaction.response.edit_message(embed=embed, view=view)
            icon = "✅" if res.get("correct") else ("🛑" if mode == "formal" else "⚠️")
            await interaction.followup.send(f"{icon} {res.get('message') or 'Accusation resolved.'}", ephemeral=True)
        return callback

    async def _abandon_selected_bounty(self, interaction: discord.Interaction):
        if not self.selected_quest_id:
            await interaction.response.send_message("No bounty selected to abandon.", ephemeral=True)
            return
        bounty = await adb(db.get_quest_by_id, self.session_id, self.selected_quest_id)
        if not bounty:
            await interaction.response.send_message("Bounty not found.", ephemeral=True)
            return
        q_notes = str(bounty.get("quest_notes") or "")
        if str(self.selected_quest_id).upper().startswith("MAND-") or "mandatory_daily:1" in q_notes:
            await interaction.response.send_message(
                "⚠️ **Mandatory Faction Dispatch!** Daily mandatory containment directives cannot be abandoned.",
                ephemeral=True,
            )
            return
        forfeit_res = await adb(
            game_engine.forfeit_side_bounty,
            self.session_id,
            self.selected_quest_id,
            [interaction.user.id],
            interaction.user.id,
        )
        if not forfeit_res.get("success"):
            await interaction.response.send_message(
                f"🔒 {forfeit_res.get('reason') or 'Cannot abandon this contract.'}",
                ephemeral=True,
            )
            return
        view, embed = await create_quest_log_view_and_embed(self.session_id, tab="Bounties", selected_quest_id=None)
        await interaction.response.edit_message(embed=embed, view=view)
        if forfeit_res.get("status") == "Failed":
            await interaction.followup.send(
                f"🛑 **Engaged Contract Forfeited:** **{bounty.get('title', 'Bounty')}** was marked **Failed** with regional fallout!",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                f"🗑️ Abandoned bounty: **{bounty.get('title', 'Bounty')}**.\nThe bounty slot is now freed up!",
                ephemeral=True
            )

    async def _open_bounty_board(self, interaction: discord.Interaction):
        session = await adb(db.get_session, self.session_id)
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


class ContractDispositionSelect(discord.ui.Select):
    def __init__(self, session_id: int, quest_id: str, dossier: dict, row: int = 3):
        self.session_id = session_id
        self.quest_id = quest_id
        twist = dossier.get("twist_spec") or {}
        t_item = dossier.get("tangible_item") or {}

        options = [
            discord.SelectOption(
                label="Deliver Contract (Standard Turn-In)",
                value="deliver",
                description="Complete the contract on standard client terms",
                emoji="📦",
            )
        ]
        if twist.get("has_twist") and twist.get("is_discovered"):
            if twist.get("side_switch_available"):
                options.append(discord.SelectOption(
                    label="Side-Switch with Twist Target (1.25x Gold)",
                    value="side_switch",
                    description="Back the uncovered twist faction instead of the client",
                    emoji="🤝",
                ))
            if twist.get("blackmail_available"):
                options.append(discord.SelectOption(
                    label="Blackmail Client for Hush-Money (2x Gold, CHA)",
                    value="blackmail_client",
                    description="Leverage incriminating twist evidence for double payout",
                    emoji="🕵️",
                ))
        if t_item.get("has_item"):
            options.append(discord.SelectOption(
                label=f"Keep '{t_item.get('name', 'Item')}' (Betray Client)",
                value="keep",
                description="Unlock quest item for personal use; triggers client retaliation",
                emoji="🎒",
            ))
            options.append(discord.SelectOption(
                label=f"Fence '{t_item.get('name', 'Item')}' (1.5x Gold)",
                value="fence",
                description="Sell quest item on the black market; spawns World Scar",
                emoji="💰",
            ))
            options.append(discord.SelectOption(
                label=f"Destroy '{t_item.get('name', 'Item')}'",
                value="destroy",
                description="Destroy dangerous or cursed payload permanently",
                emoji="🔥",
            ))
        super().__init__(placeholder="Resolve / Turn-In Contract...", min_values=1, max_values=1, options=options, row=row)

    async def callback(self, interaction: discord.Interaction):
        disp = self.values[0]
        sess = await adb(db.get_session, self.session_id) or {}
        res = await adb(
            game_engine.resolve_quest_turn_in_or_betrayal,
            self.session_id,
            self.quest_id,
            interaction.user.id,
            disp,
            None,
            str(sess.get("current_location") or ""),
        )
        if not res.get("success"):
            await interaction.response.send_message(f"⚠️ {res.get('reason') or 'Cannot resolve turn-in yet.'}", ephemeral=True)
            return
        view, embed = await create_quest_log_view_and_embed(self.session_id, tab="Bounties", selected_quest_id=None)
        await interaction.response.edit_message(embed=embed, view=view)
        gold_note = f" (`+{res.get('gold_awarded', 0)}G`)" if res.get("gold_awarded") else ""
        await interaction.followup.send(
            f"📜 **Contract Resolution ({disp.replace('_', ' ').title()}):** Status `{res.get('quest_status', 'Resolved')}`{gold_note}",
            ephemeral=True,
        )


class BountySelect(discord.ui.Select):
    def __init__(self, session_id: int, bounties: list[dict], haggle_advance: bool = False):
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
        self.haggle_advance = haggle_advance

    async def callback(self, interaction: discord.Interaction):
        quest_id = self.values[0]
        quest = await adb(db.get_quest_by_id, self.session_id, quest_id)
        if not quest or quest.get("status") != "Available":
            await interaction.response.send_message("That bounty is no longer available.", ephemeral=True)
            return

        session = await adb(db.get_session, self.session_id) or {"id": self.session_id}
        import scenario_data
        if scenario_data.is_anomalous_incursions_scenario(session.get("scenario", "")):
            from mechanics.narrative.bounty import evaluate_anomalous_bounty_eligibility
            elig = await adb(evaluate_anomalous_bounty_eligibility, self.session_id, interaction.user.id, quest)
            if not elig.get("allowed", True):
                await interaction.response.send_message(
                    f"🔒 **Contract Restricted:** {elig.get('reason') or 'Your current faction affiliation prohibits accepting this contract.'}",
                    ephemeral=True,
                )
                return

        acc_res = await game_engine.accept_bounty_contract_async(
            session_id=self.session_id,
            quest_id=quest_id,
            user_id=interaction.user.id,
            haggle_advance=bool(self.haggle_advance),
            enrich_llm=False,
        )
        if not acc_res.get("success"):
            await interaction.response.send_message(
                f"⚠️ {acc_res.get('reason') or 'Cannot accept this bounty right now.'}",
                ephemeral=True,
            )
            return

        remaining_bounties = await adb(db.get_session_quests, self.session_id, "Available")
        embed = _build_bounty_board_embed(session, remaining_bounties)
        view = BountyBoardView(session, remaining_bounties, haggle_advance=self.haggle_advance)

        adv = acc_res.get("advance_result") or {}
        adv_line = f"\n💰 **Upfront Advance Secured:** `+{adv['advance_gold']}G`!" if adv.get("succeeded") else ""

        await interaction.response.edit_message(embed=embed, view=view)
        await interaction.followup.send(
            f"🎯 **Bounty Accepted!** Added **{quest['title']}** to your active Quest Log.{adv_line}\n"
            f"Objective: {quest['objective']}",
            ephemeral=True
        )


class BountyBoardView(discord.ui.View):
    def __init__(self, session: dict, bounties: list[dict], haggle_advance: bool = False):
        super().__init__(timeout=300)
        self.session = session
        self.session_id = session["id"]
        self.haggle_advance = haggle_advance

        if bounties:
            self.add_item(BountySelect(self.session_id, bounties, haggle_advance=haggle_advance))

        refresh_btn = discord.ui.Button(label="Refresh Board", emoji="🔄", style=discord.ButtonStyle.primary)
        haggle_btn = discord.ui.Button(
            label="Advance (CHA): ON" if haggle_advance else "Advance (CHA): OFF",
            emoji="💰",
            style=discord.ButtonStyle.success if haggle_advance else discord.ButtonStyle.secondary,
        )
        quest_btn = discord.ui.Button(label="Quest Log", emoji="📜", style=discord.ButtonStyle.secondary)

        refresh_btn.callback = self._refresh_board
        haggle_btn.callback = self._toggle_haggle_advance
        quest_btn.callback = self._open_quest_log

        self.add_item(refresh_btn)
        self.add_item(haggle_btn)
        self.add_item(quest_btn)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        turn_order = (self.session or {}).get("turn_order") or []
        if turn_order and interaction.user.id not in turn_order:
            await interaction.response.send_message("You're not in this session.", ephemeral=True)
            return False
        return True

    async def _toggle_haggle_advance(self, interaction: discord.Interaction):
        self.haggle_advance = not self.haggle_advance
        bounties = await adb(db.get_session_quests, self.session_id, "Available")
        embed = _build_bounty_board_embed(self.session, bounties)
        view = BountyBoardView(self.session, bounties, haggle_advance=self.haggle_advance)
        await interaction.response.edit_message(embed=embed, view=view)

    async def _refresh_board(self, interaction: discord.Interaction):
        await interaction.response.defer()
        new_bounties = await game_engine.generate_bounty_board(self.session, force_refresh=True)
        embed = _build_bounty_board_embed(self.session, new_bounties)
        view = BountyBoardView(self.session, new_bounties, haggle_advance=self.haggle_advance)
        await interaction.followup.edit_message(message_id=interaction.message.id, embed=embed, view=view)

    async def _open_quest_log(self, interaction: discord.Interaction):
        view, embed = await create_quest_log_view_and_embed(self.session_id, tab="Main Quest")
        await interaction.response.edit_message(embed=embed, view=view)

