"""Shared Discord picker for scenario variants (second step after choosing a scenario family).

Not a cog: imported by `cogs.adventure` (/adventure start) and `cogs.character`
(/character create). Family/variant data comes from `scenario_variants` so the
grouping matches the web Embarkation Wizard.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable

import discord

import scenario_variants

VariantPickCallback = Callable[[discord.Interaction, str], Awaitable[Any]]


def channel_allows_nsfw(channel: Any) -> bool:
    """True when NSFW/gore variants may be offered in `channel`.

    Guild text channels and threads must be age-restricted. DMs (which have no
    `is_nsfw` in discord.py) stay allowed, matching existing behavior.
    """
    is_nsfw = getattr(channel, "is_nsfw", None)
    if not callable(is_nsfw):
        return True
    try:
        return bool(is_nsfw())
    except Exception:
        return False


def offered_variants(root_key: str, allow_nsfw: bool) -> list[dict[str, Any]]:
    variants = scenario_variants.get_family_variants(root_key)
    return [v for v in variants if allow_nsfw or not v["is_nsfw"]]


def needs_variant_step(root_key: str, allow_nsfw: bool) -> bool:
    return len(offered_variants(root_key, allow_nsfw)) > 1


def hidden_nsfw_note(root_key: str, allow_nsfw: bool) -> str:
    if allow_nsfw:
        return ""
    hidden = len(scenario_variants.get_family_variants(root_key)) - len(offered_variants(root_key, False))
    if hidden <= 0:
        return ""
    return f"\n-# 🔞 {hidden} mature variant(s) are only listed in age-restricted channels or DMs."


class ScenarioVariantSelectView(discord.ui.View):
    """Single Select listing every variant of a scenario family; hands the chosen key to `on_pick`."""

    def __init__(self, user_id: int, root_key: str, on_pick: VariantPickCallback,
                 *, allow_nsfw: bool = True, timeout: float = 180):
        super().__init__(timeout=timeout)
        self.user_id = user_id
        self.on_pick = on_pick
        options = []
        for v in offered_variants(root_key, allow_nsfw)[:25]:
            tag_hint = " • ".join(v["variant_tag_labels"])
            desc = v["description"] or tag_hint
            options.append(discord.SelectOption(
                label=str(v["variant_label"])[:100],
                value=v["key"],
                description=(desc[:100] if desc else None),
                emoji=(v["emoji"][:1] if v["emoji"] else None),
            ))
        select = discord.ui.Select(placeholder="Choose a variant...", options=options, min_values=1, max_values=1)
        select.callback = self._on_select
        self.add_item(select)

    async def _on_select(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This picker isn't yours.", ephemeral=True)
            return
        self.stop()
        await self.on_pick(interaction, interaction.data["values"][0])
