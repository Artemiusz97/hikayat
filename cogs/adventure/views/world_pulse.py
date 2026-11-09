from __future__ import annotations

import time
from typing import Any

import discord

import db
from db import adb
from .base import SessionRestrictedView
from mechanics.system.concurrency import distributed_session_lock
from mechanics.world.world_events import build_client_world_pulse_payload


def _format_remaining_time(item: dict, current_day: int, current_minute: int) -> str:
    exp_day = int(item.get("expires_day") or current_day or 1)
    exp_min = int(item.get("expires_minute") or current_minute or 480)
    now_total = (int(current_day or 1) * 1440) + int(current_minute or 480)
    exp_total = (exp_day * 1440) + exp_min
    diff_mins = max(0, exp_total - now_total)
    total_hours = max(1, (diff_mins + 59) // 60)
    days, hours = divmod(total_hours, 24)
    if days > 0:
        return f"{days}d {hours}h left"
    return f"{total_hours}h left"


def build_world_pulse_embed(
    session_id: int,
    filter_mode: str = "all",
    payload: dict[str, Any] | None = None,
) -> discord.Embed:
    """Builds the Discord World Pulse embed strictly from fog-of-war-safe discovered state."""
    if payload is None:
        payload = build_client_world_pulse_payload(session_id)
    cur_day = int(payload.get("current_day") or 1)
    cur_min = int(payload.get("current_minute") or 480)
    macros = list(payload.get("active_macro_events") or [])
    rumors = [r for r in (payload.get("active_rumors") or []) if bool(r.get("is_discovered"))]
    minors = list(payload.get("active_minor_events") or [])
    tracked_cnt = int(payload.get("tracked_rumor_count") or 0)
    max_tracked = int(payload.get("max_tracked_rumors") or 2)
    tracked_mnr_cnt = int(payload.get("tracked_minor_bounty_count") or 0)
    max_tracked_mnr = int(payload.get("max_tracked_minor_bounties") or 2)

    embed = discord.Embed(
        title="🌐 World Pulse — Regional Events & Whispered Rumors",
        description=(
            f"📅 **Day {cur_day}** • 🔎 **Active Rumor Investigations:** `{tracked_cnt}/{max_tracked}` • 🎯 **Minor Bounties:** `{tracked_mnr_cnt}/{max_tracked_mnr}`\n"
            f"*Discover new rumors through NPC banter, notice boards, or scouring your social gossip feed.*"
        ),
        color=discord.Color.blurple(),
    )

    if filter_mode in ("all", "events"):
        if macros:
            lines = []
            for ev in macros[:6]:
                is_aftermath = ev.get("status") == "resolved_aftermath"
                badge = "🟢 Aftermath Buzz" if is_aftermath else f"✨ {str(ev.get('event_subtype') or 'Event').title()}"
                rem = _format_remaining_time(ev, cur_day, cur_min)
                loc = f" • 📍 *{ev['location_name']}*" if ev.get("location_name") else ""
                lines.append(f"**{ev.get('title', 'World Event')}** (`{badge}` • ⏳ `{rem}`){loc}\n{ev.get('description', '')}")
            embed.add_field(
                name=f"🌍 Active World Events ({len(macros)})",
                value="\n\n".join(lines)[:1024],
                inline=False,
            )
        elif filter_mode == "events" and not minors:
            embed.add_field(
                name="🌍 Active World Events",
                value="*No macro world events are active right now.*",
                inline=False,
            )
        if minors:
            m_lines = []
            for mv in minors[:4]:
                is_aftermath = mv.get("status") == "resolved_aftermath"
                badge = "🟢 Resolved Buzz" if is_aftermath else "📌 Local Chatter"
                if bool(mv.get("linked_quest_id")) and not is_aftermath:
                    badge += " (Investigating)"
                rem = _format_remaining_time(mv, cur_day, cur_min)
                loc = f" • 📍 *{mv['location_name']}*" if mv.get("location_name") else ""
                m_lines.append(f"**{mv.get('title', 'Local Chatter')}** (`{badge}` • ⏳ `{rem}`){loc}\n{mv.get('description', '')}")
            embed.add_field(
                name=f"📌 Local Chatter & Incidents ({len(minors)})",
                value="\n\n".join(m_lines)[:1024],
                inline=False,
            )

    if filter_mode in ("all", "rumors"):
        if rumors:
            r_lines = []
            for rm in rumors[:6]:
                is_aftermath = rm.get("status") == "resolved_aftermath"
                is_tracked = bool(rm.get("linked_quest_id"))
                status_tag = (
                    "🟢 Resolved Buzz"
                    if is_aftermath
                    else ("🧭 Investigating" if is_tracked else "🗣️ Unverified Lead")
                )
                rem = _format_remaining_time(rm, cur_day, cur_min)
                loc = f" • 📍 *{rm['location_name']}*" if rm.get("location_name") else ""
                r_lines.append(f"**{rm.get('title', 'Rumor')}** (`{status_tag}` • ⏳ `{rem}`){loc}\n{rm.get('description', '')}")
            embed.add_field(
                name=f"🕵️ Known Local Rumors ({len(rumors)})",
                value="\n\n".join(r_lines)[:1024],
                inline=False,
            )
        elif filter_mode == "rumors":
            embed.add_field(
                name="🕵️ Known Local Rumors",
                value="*You haven't uncovered any active local rumors yet.*",
                inline=False,
            )

    if not embed.fields:
        embed.add_field(
            name="Quiet Horizon",
            value="*No active world events or discovered rumors at this moment.*",
            inline=False,
        )

    return embed


class RumorTrackSelect(discord.ui.Select):
    """Dedicated row=0 dropdown to accept an untracked discovered rumor investigation or claimable minor bounty."""

    def __init__(self, session_id: int, user_id: int, rumors: list[dict], filter_mode: str = "all"):
        options = []
        for rm in rumors[:25]:
            key = str(rm.get("event_key") or "")
            if not key:
                continue
            is_minor = rm.get("entity_type") == "minor_event"
            prefix = "[Mundane] " if is_minor else ""
            emoji = "📌" if is_minor else "🧭"
            title = f"{prefix}{str(rm.get('title') or 'Local Rumor')}"[:100]
            desc = str(rm.get("description") or "Track this lead in your Quest Log")[:100]
            options.append(
                discord.SelectOption(
                    label=title,
                    value=key,
                    description=desc,
                    emoji=emoji,
                )
            )
        if filter_mode == "events":
            ph = "📌 Track a minor incident bounty (Max 2 active)..."
        elif filter_mode == "rumors":
            ph = "🧭 Track a discovered rumor lead (Max 2 active)..."
        else:
            ph = "🧭 Track a rumor lead or minor incident (Max 2 each)..."
        super().__init__(
            placeholder=ph,
            min_values=1,
            max_values=1,
            options=options,
            row=0,
        )
        self.session_id = session_id
        self.user_id = user_id
        self.filter_mode = filter_mode

    async def callback(self, interaction: discord.Interaction):
        vals = list(self.values) or list((getattr(interaction, "data", None) or {}).get("values") or [])
        if not vals:
            return
        event_key = str(vals[0])
        try:
            async with distributed_session_lock(self.session_id):
                session = await adb(db.get_session, self.session_id) or {}
                c_day, c_min, _ = await adb(db.get_session_time, self.session_id)
                turn_num = await adb(db.infer_session_turn, session)
                await adb(
                    db.claim_rumor_investigation,
                    self.session_id,
                    event_key,
                    int(c_day),
                    int(c_min),
                    int(turn_num),
                )
        except ValueError as exc:
            msg = f"⚠️ {exc}"
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
            return

        payload = await adb(build_client_world_pulse_payload, self.session_id)
        try:
            from api.deps import manager
            await manager.broadcast(
                self.session_id,
                {
                    "type": "WORLD_PULSE_SYNC",
                    "session_id": int(self.session_id),
                    "world_pulse": payload,
                    "sync_timestamp": time.time(),
                },
            )
        except Exception:
            pass
        embed = build_world_pulse_embed(self.session_id, self.filter_mode, payload=payload)
        uid = interaction.user.id if getattr(interaction, "user", None) else self.user_id
        view = WorldPulseView(self.session_id, uid, filter_mode=self.filter_mode, payload=payload)
        await interaction.response.edit_message(embed=embed, view=view)


class WorldPulseView(SessionRestrictedView):
    """Discord World Pulse interactive view with row=0 Select and row=1 filter/refresh buttons."""

    def __init__(
        self,
        session_id: int,
        user_id: int,
        filter_mode: str = "all",
        payload: dict[str, Any] | None = None,
    ):
        super().__init__(session_id=session_id, timeout=300)
        self.session_id = session_id
        self.user_id = user_id
        self.filter_mode = filter_mode if filter_mode in ("all", "events", "rumors") else "all"

        if payload is None:
            payload = build_client_world_pulse_payload(session_id)
        self.payload = payload
        discovered_rumors = [
            r for r in (payload.get("active_rumors") or [])
            if bool(r.get("is_discovered"))
            and r.get("status") == "active"
            and not r.get("linked_quest_id")
        ]
        claimable_minors = []
        if payload.get("can_track_minor_bounty", True):
            claimable_minors = [
                m for m in (payload.get("active_minor_events") or [])
                if m.get("status") == "active"
                and not m.get("linked_quest_id")
                and bool((m.get("metadata") or {}).get("can_spawn_bounty"))
            ]
        all_trackable: list[dict] = []
        if self.filter_mode in ("all", "rumors") and payload.get("can_track_rumor", True):
            all_trackable.extend(discovered_rumors)
        if self.filter_mode in ("all", "events") and payload.get("can_track_minor_bounty", True):
            all_trackable.extend(claimable_minors)
        if all_trackable:
            self.add_item(RumorTrackSelect(session_id, user_id, all_trackable[:25], filter_mode=self.filter_mode))

        all_btn = discord.ui.Button(
            label="All",
            emoji="🌐",
            style=discord.ButtonStyle.primary if self.filter_mode == "all" else discord.ButtonStyle.secondary,
            row=1,
        )
        ev_btn = discord.ui.Button(
            label="Events",
            emoji="🌍",
            style=discord.ButtonStyle.primary if self.filter_mode == "events" else discord.ButtonStyle.secondary,
            row=1,
        )
        rm_btn = discord.ui.Button(
            label="Rumors",
            emoji="🕵️",
            style=discord.ButtonStyle.primary if self.filter_mode == "rumors" else discord.ButtonStyle.secondary,
            row=1,
        )
        refresh_btn = discord.ui.Button(
            label="Refresh",
            emoji="🔄",
            style=discord.ButtonStyle.secondary,
            row=1,
        )

        all_btn.callback = self._make_filter_cb("all")
        ev_btn.callback = self._make_filter_cb("events")
        rm_btn.callback = self._make_filter_cb("rumors")
        refresh_btn.callback = self._make_filter_cb(self.filter_mode)

        self.add_item(all_btn)
        self.add_item(ev_btn)
        self.add_item(rm_btn)
        self.add_item(refresh_btn)

    def _make_filter_cb(self, mode: str):
        async def _cb(interaction: discord.Interaction):
            payload = await adb(build_client_world_pulse_payload, self.session_id)
            embed = build_world_pulse_embed(self.session_id, mode, payload=payload)
            uid = interaction.user.id if getattr(interaction, "user", None) else self.user_id
            view = WorldPulseView(self.session_id, uid, filter_mode=mode, payload=payload)
            await interaction.response.edit_message(embed=embed, view=view)

        return _cb
