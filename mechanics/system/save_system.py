from __future__ import annotations
"""
Mechanics module for Campaign / Slot Saving System in Hikayat.
Handles slot name validation, timestamp formatting, visual embed generation,
and interactive Discord UI views (SaveManagerView, OverwriteConfirmView, LoadConfirmView, DeleteSaveConfirmView).
"""
import re
import datetime
import discord

import db
from db import adb


def validate_slot_name(slot_name: str) -> str:
    """Validates and sanitizes a save slot name."""
    cleaned = (slot_name or "").strip()
    if not cleaned:
        raise ValueError("Save slot name cannot be empty.")
    if len(cleaned) > 32:
        raise ValueError("Save slot name cannot exceed 32 characters.")
    if not re.match(r"^[\w\s\-]+$", cleaned, re.UNICODE):
        raise ValueError("Save slot name contains invalid characters. Use letters, numbers, spaces, hyphens, or underscores.")
    return cleaned


def format_save_timestamp(epoch_time: float) -> str:
    """Formats epoch timestamp into readable string and Discord relative timestamp."""
    dt = datetime.datetime.fromtimestamp(epoch_time, tz=datetime.timezone.utc)
    readable = dt.strftime("%b %d, %Y - %H:%M UTC")
    discord_ts = f"<t:{int(epoch_time)}:R>"
    return f"{readable} ({discord_ts})"


def build_save_slot_embed(save_meta: dict, char: dict = None) -> discord.Embed:
    """Builds a detailed preview card for a single save slot."""
    slot_name = save_meta.get("slot_name", "Unknown Slot")
    scenario = str(save_meta.get("scenario", "fantasy")).title()
    scene_title = save_meta.get("scene_title") or "Adventure Continues"
    location = save_meta.get("current_location") or "Unknown Area"
    snippet = save_meta.get("narrative_snippet") or "*No preview narrative available.*"
    saved_at = save_meta.get("saved_at", 0)

    embed = discord.Embed(
        title=f"💾 Save Slot: {slot_name}",
        description=f"> *\"{snippet}\"*",
        color=discord.Color.blue()
    )

    embed.add_field(name="📖 Scenario", value=f"`{scenario}`", inline=True)
    embed.add_field(name="📍 Location", value=f"**{location}**", inline=True)
    embed.add_field(name="🎬 Scene", value=f"*{scene_title}*", inline=True)

    if char:
        embed.add_field(
            name="👤 Hero",
            value=f"**{char['name']}** (Lvl {char['level']} {char['char_class']})",
            inline=True
        )
        embed.add_field(
            name="❤️ Vitals",
            value=f"HP {char['hp']}/{char['max_hp']} | MP {char['mp']}/{char['max_mp']}",
            inline=True
        )
        embed.add_field(name="🪙 Gold", value=f"{char.get('gold', 0)}g", inline=True)

    embed.add_field(name="🕒 Saved At", value=format_save_timestamp(saved_at), inline=False)
    embed.set_footer(text="Use /adventure load to restore this checkpoint or /adventure saves to view all slots.")
    return embed


def build_saves_list_embed(saves: list[dict], char: dict) -> discord.Embed:
    """Builds an overview embed listing all saved checkpoints for the active character."""
    embed = discord.Embed(
        title=f"💾 Adventure Checkpoints: {char['name']}",
        description=f"Showing **{len(saves)}/10** saved adventure slots for **{char['name']}**.\n"
                    f"Select a slot below to inspect details, load, or delete.",
        color=discord.Color.gold()
    )

    if not saves:
        embed.description = (
            f"You have no saved checkpoints for **{char['name']}** yet.\n\n"
            f"💡 While on an active adventure, use `/adventure save [name]` to save your current story progress!"
        )
        embed.set_footer(text="Save slots are isolated per character (up to 10 slots each).")
        return embed

    for idx, s in enumerate(saves, start=1):
        slot = s["slot_name"]
        scen = str(s.get("scenario", "fantasy")).title()
        loc = s.get("current_location") or "Wilderness"
        title = s.get("scene_title") or "Adventure"
        ts_rel = f"<t:{int(s['saved_at'])}:R>"
        
        snippet = s.get("narrative_snippet") or ""
        short_snippet = (snippet[:100] + "...") if len(snippet) > 100 else snippet

        field_value = (
            f"**Scenario:** `{scen}` | **Location:** {loc}\n"
            f"**Scene:** *{title}* ({ts_rel})\n"
        )
        if short_snippet:
            field_value += f"> *{short_snippet}*"

        embed.add_field(
            name=f"{idx}. 🏷️ {slot}",
            value=field_value,
            inline=False
        )

    embed.set_footer(text="Use the dropdown or buttons below to manage your adventure checkpoints.")
    return embed


# ==============================================================================
# UI VIEWS
# ==============================================================================

class SaveSlotSelectDropdown(discord.ui.Select):
    def __init__(self, saves: list[dict], selected_slot: str | None = None):
        options = []
        for s in saves[:25]:
            slot = s["slot_name"]
            scen = str(s.get("scenario", "fantasy")).title()
            title = (s.get("scene_title") or "Adventure")[:30]
            options.append(discord.SelectOption(
                label=f"{slot}"[:100],
                value=slot,
                description=f"[{scen}] {title}"[:100],
                emoji="💾",
                default=(slot == selected_slot)
            ))
        super().__init__(
            placeholder="Select a save slot to inspect or load...",
            min_values=1,
            max_values=1,
            options=options,
            row=0
        )

    async def callback(self, interaction: discord.Interaction):
        view: SaveManagerView = self.view
        selected = self.values[0]
        view.selected_slot = selected
        save_meta = await adb(db.get_adventure_save_metadata, view.user_id, selected)
        char = await adb(db.get_character, view.user_id)
        if not save_meta:
            await interaction.response.send_message("❌ Save slot not found.", ephemeral=True)
            return

        embed = build_save_slot_embed(save_meta, char)
        view.update_buttons()
        await interaction.response.edit_message(embed=embed, view=view)


class SaveManagerView(discord.ui.View):
    def __init__(self, cog, user_id: int, saves: list[dict], selected_slot: str | None = None):
        super().__init__(timeout=180)
        self.cog = cog
        self.user_id = user_id
        self.saves = saves
        self.selected_slot = selected_slot

        if saves:
            self.dropdown = SaveSlotSelectDropdown(saves, selected_slot)
            self.add_item(self.dropdown)

        self.update_buttons()

    def update_buttons(self):
        # Clear existing action buttons (rows >= 1)
        self.children = [c for c in self.children if isinstance(c, discord.ui.Select)]

        if self.selected_slot:
            load_btn = discord.ui.Button(
                label=f"Load '{self.selected_slot}'",
                style=discord.ButtonStyle.success,
                emoji="▶️",
                row=1
            )
            load_btn.callback = self._on_load_clicked
            self.add_item(load_btn)

            del_btn = discord.ui.Button(
                label="Delete Slot",
                style=discord.ButtonStyle.danger,
                emoji="🗑️",
                row=1
            )
            del_btn.callback = self._on_delete_clicked
            self.add_item(del_btn)

        if self.saves and self.selected_slot:
            back_btn = discord.ui.Button(
                label="Overview List",
                style=discord.ButtonStyle.secondary,
                emoji="📋",
                row=1
            )
            back_btn.callback = self._on_back_clicked
            self.add_item(back_btn)

    async def _on_load_clicked(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your session.", ephemeral=True)
            return

        active_id = await adb(db.get_active_session_id_for_user, self.user_id)
        if active_id:
            # Confirm overwrite of active session
            view = LoadConfirmView(self.cog, self.user_id, self.selected_slot)
            await interaction.response.send_message(
                f"⚠️ You currently have an active adventure in progress! Loading checkpoint **{self.selected_slot}** "
                f"will replace your current active adventure. Do you want to proceed?",
                view=view,
                ephemeral=True
            )
            return

        await interaction.response.defer()
        try:
            session = await adb(db.load_adventure_slot, self.user_id, self.selected_slot)
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to load save slot: {e}", ephemeral=True)
            return

        await interaction.followup.send(f"✅ Successfully loaded checkpoint **{self.selected_slot}**!")
        await self.cog._resend_current_scene(interaction, session, use_followup=True)

    async def _on_delete_clicked(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your session.", ephemeral=True)
            return

        view = DeleteSaveConfirmView(self.cog, self.user_id, self.selected_slot, parent_view=self)
        await interaction.response.send_message(
            f"⚠️ Are you sure you want to permanently delete save slot **{self.selected_slot}**? This cannot be undone.",
            view=view,
            ephemeral=True
        )

    async def _on_back_clicked(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your session.", ephemeral=True)
            return

        self.selected_slot = None
        char = await adb(db.get_character, self.user_id)
        self.saves = await adb(db.list_adventure_saves, self.user_id)
        self.update_buttons()
        embed = build_saves_list_embed(self.saves, char)
        await interaction.response.edit_message(embed=embed, view=self)


class OverwriteConfirmView(discord.ui.View):
    def __init__(self, cog, user_id: int, slot_name: str):
        super().__init__(timeout=60)
        self.cog = cog
        self.user_id = user_id
        self.slot_name = slot_name

    @discord.ui.button(label="Overwrite Save", style=discord.ButtonStyle.danger, emoji="💾")
    async def confirm_overwrite(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your prompt.", ephemeral=True)
            return

        try:
            res = await adb(db.save_adventure_slot, self.user_id, self.slot_name, overwrite=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed to save: {e}", ephemeral=True)
            return

        for child in self.children:
            child.disabled = True
        msg = f"💾 Overwrote save slot **{res['slot_name']}** at location **{res['current_location'] or 'Wilderness'}**!"
        await interaction.response.edit_message(content=msg, view=self)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your prompt.", ephemeral=True)
            return

        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="Save cancelled.", view=self)
        self.stop()


class LoadConfirmView(discord.ui.View):
    def __init__(self, cog, user_id: int, slot_name: str):
        super().__init__(timeout=60)
        self.cog = cog
        self.user_id = user_id
        self.slot_name = slot_name

    @discord.ui.button(label="Proceed & Load Checkpoint", style=discord.ButtonStyle.primary, emoji="▶️")
    async def confirm_load(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your confirmation.", ephemeral=True)
            return

        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content=f"🔄 Loading checkpoint **{self.slot_name}**...", view=self)

        try:
            session = await adb(db.load_adventure_slot, self.user_id, self.slot_name)
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to load save slot: {e}", ephemeral=True)
            return

        await interaction.followup.send(f"✅ Successfully loaded checkpoint **{self.slot_name}**!")
        await self.cog._resend_current_scene(interaction, session, use_followup=True)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your confirmation.", ephemeral=True)
            return

        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="Load cancelled. Your current adventure remains active.", view=self)
        self.stop()


class DeleteSaveConfirmView(discord.ui.View):
    def __init__(self, cog, user_id: int, slot_name: str, parent_view: SaveManagerView | None = None):
        super().__init__(timeout=60)
        self.cog = cog
        self.user_id = user_id
        self.slot_name = slot_name
        self.parent_view = parent_view

    @discord.ui.button(label="Confirm Delete", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def confirm_delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your confirmation.", ephemeral=True)
            return

        deleted = await adb(db.delete_adventure_save, self.user_id, self.slot_name)
        for child in self.children:
            child.disabled = True

        if deleted:
            msg = f"🗑️ Permanently deleted save slot **{self.slot_name}**."
        else:
            msg = f"❌ Could not find save slot **{self.slot_name}** to delete."

        await interaction.response.edit_message(content=msg, view=self)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your confirmation.", ephemeral=True)
            return

        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="Deletion cancelled.", view=self)
        self.stop()
