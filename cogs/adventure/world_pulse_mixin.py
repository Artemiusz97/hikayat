from __future__ import annotations

import discord

import db
from db import adb
from mechanics.world.world_events.engine import build_client_world_pulse_payload
from .views.world_pulse import WorldPulseView, build_world_pulse_embed


class WorldPulseMixin:
    """World Pulse handlers for AdventureCog (/world and /adventure world_pulse)."""

    async def _do_world_pulse(self, interaction: discord.Interaction) -> None:
        char = await adb(db.get_character, interaction.user.id)
        if not char:
            msg = "You need a character first. Use `/character create`."
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
            return

        session_id = await adb(db.get_active_session_id_for_user, interaction.user.id)
        if not session_id:
            msg = "No active adventure. Start one with `/adventure start` or `/adventure custom`."
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
            return

        session = await adb(db.get_session, session_id)
        if not session or session.get("status") != "active":
            msg = "No active adventure session found."
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
            return

        payload = await adb(build_client_world_pulse_payload, session_id)
        embed = build_world_pulse_embed(session_id, "all", payload=payload)
        view = WorldPulseView(session_id, interaction.user.id, filter_mode="all", payload=payload)
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
