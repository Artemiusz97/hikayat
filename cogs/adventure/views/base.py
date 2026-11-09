from __future__ import annotations

from typing import Iterable, Optional
import discord

import db
from db import adb


class SessionRestrictedView(discord.ui.View):
    """Base Discord UI View enforcing session party membership (or explicit owner restriction)."""

    def __init__(
        self,
        *,
        session_id: int,
        timeout: Optional[float] = 180,
        owner_user_id: Optional[int] = None,
        allowed_user_ids: Optional[Iterable[int]] = None,
    ):
        super().__init__(timeout=timeout)
        self.session_id = int(session_id or 0)
        self.owner_user_id = int(owner_user_id) if owner_user_id is not None else None
        self.allowed_user_ids = (
            {int(uid) for uid in allowed_user_ids if uid is not None}
            if allowed_user_ids is not None
            else None
        )

    async def _resolve_party_user_ids(self) -> set[int]:
        if self.allowed_user_ids:
            return set(self.allowed_user_ids)
        if not self.session_id:
            return set()

        def _load_ids(sid: int) -> set[int]:
            ids: set[int] = set()
            for m_uid in (db.get_session_members(sid) or []):
                if m_uid is not None:
                    ids.add(int(m_uid))
            sess = db.get_session(sid) or {}
            for t_uid in (sess.get("turn_order") or []):
                if t_uid is not None:
                    ids.add(int(t_uid))
            host_uid = sess.get("host_user_id")
            if host_uid is not None:
                ids.add(int(host_uid))
            return ids

        return await adb(_load_ids, self.session_id)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        caller_id = int(getattr(getattr(interaction, "user", None), "id", 0) or 0)
        if not caller_id:
            return False

        if self.owner_user_id is not None:
            if caller_id != self.owner_user_id:
                if interaction.response.is_done() is not True:
                    await interaction.response.send_message(
                        f"This menu belongs to <@{self.owner_user_id}>.",
                        ephemeral=True,
                    )
                return False
            return True

        party_ids = await self._resolve_party_user_ids()
        if not party_ids or caller_id not in party_ids:
            if interaction.response.is_done() is not True:
                await interaction.response.send_message(
                    "You're not in this session.",
                    ephemeral=True,
                )
            return False
        return True
