from __future__ import annotations

"""
Discord UI Views & Embeds for Entity Contracts & Devil Pacts (`anomalous_incursions`,
`anomalous_high_school`, and all `gore` / `furry` / `nsfw` variants).
"""

from typing import Any, Dict, List, Optional

import discord

import db
from db import adb
from localization import get_pact_ui_label
from mechanics.pacts import build_contracts_overview_payload, execute_pact_ritual_action
from mechanics.system.concurrency import distributed_adventure_lock
from .base import SessionRestrictedView

_ROMAN_TIERS: Dict[int, str] = {1: "I", 2: "II", 3: "III"}


def _format_stat_locks(stat_locks: Optional[Dict[str, Any]], max_hp_lock_pct: float = 0.0) -> str:
    tokens: List[str] = []
    if max_hp_lock_pct and float(max_hp_lock_pct) > 0:
        tokens.append(f"-{int(round(float(max_hp_lock_pct) * 100))}% Max HP")
    for k, v in (stat_locks or {}).items():
        try:
            iv = int(v)
        except (TypeError, ValueError):
            continue
        if iv != 0:
            tokens.append(f"{iv:+d} {str(k).upper()}")
    return " • ".join(tokens) if tokens else "None"


def build_entity_contracts_embed(
    overview: Dict[str, Any],
    *,
    tab: str = "active",
    selected_patron_id: Optional[str] = None,
    lang: str = "en",
) -> discord.Embed:
    """Builds the Discord embed for Active Covenants, Discovery & Appraisal, or Patron Compendium."""
    title = f"🩸 {get_pact_ui_label('title', lang)}"
    slot_used = int(overview.get("slot_used") or 0)
    slot_cap = int(overview.get("slot_capacity") or 2)
    remote_ok = bool(overview.get("remote_communion_available"))
    remote_txt = get_pact_ui_label("remote_ready" if remote_ok else "remote_blocked", lang)
    grudges = list(overview.get("active_grudges") or [])

    desc_lines = [
        f"🩸 **{get_pact_ui_label('slots_label', lang)}:** `{slot_used}/{slot_cap}` • 📡 *{remote_txt}*",
    ]
    if grudges:
        desc_lines.append(f"💀 **Active Spurned Grudge Nemeses:** `{len(grudges)}`")

    embed = discord.Embed(
        title=title,
        description="\n".join(desc_lines),
        color=discord.Color.brand_red() if tab == "active" else discord.Color.dark_gold(),
    )

    if tab == "active":
        active_pacts = list(overview.get("active_pacts") or [])
        if not active_pacts:
            embed.add_field(
                name=get_pact_ui_label("tab_active", lang),
                value="*No active Entity Contracts bound. Switch to **Discover & Appraise** at a Vault, Crimson Auction, Campus Mystery, or Boss Surrender.*",
                inline=False,
            )
            return embed

        for pact in active_pacts[:6]:
            pid = str(pact.get("patron_id") or "")
            marker = "👉 " if pid == selected_patron_id else ""
            t_num = int(pact.get("tier") or 1)
            t_rom = _ROMAN_TIERS.get(t_num, str(t_num))
            sp = pact.get("combat_skill") or {}
            cast_c = pact.get("cast_costs") or {}
            f_util = pact.get("field_utility") or {}
            locks_txt = _format_stat_locks(pact.get("stat_locks"), float(pact.get("max_hp_lock_pct") or 0.0))
            breach = int(pact.get("breach_stage") or 0)
            debt = int(pact.get("unpaid_blood_debt") or 0)

            lines = [
                f"**Element:** `{str(pact.get('element', 'aether')).title()}` ({pact.get('synergy_stat', 'INT')}) • **Appraisal:** `{pact.get('appraisal_state', 'neutral').title()}`",
                f"**0-MP Skill:** {sp.get('emoji', '🩸')} **{sp.get('name', 'Invocation')}** (`0 MP` • `{cast_c.get('hp_cost', 0)} HP`) — {sp.get('description', '')}",
                f"**Field Utility:** ✨ **{f_util.get('name', 'Passive')}** — {f_util.get('description', '')}",
                f"**Locks:** `{locks_txt}`" + (f" • 🔒 `[Pact-Bound: {pact['bound_gear_slot']}]`" if pact.get("bound_gear_slot") else ""),
            ]
            if pact.get("taboo_desc"):
                lines.append(f"⚠️ **Taboo:** {pact['taboo_desc']}")
            if breach > 0 or debt > 0:
                lines.append(f"🚨 **{get_pact_ui_label('breach_stage_1', lang)}** (`Debt: {debt}`)")
            embed.add_field(
                name=f"{marker}{pact.get('name', pid)} — Tier {t_rom}"[:256],
                value="\n".join(lines)[:1024],
                inline=False,
            )
        return embed

    if tab == "discover":
        channels = list(overview.get("channels_active") or [])
        offers = list(overview.get("available_patrons") or [])
        if channels:
            ch_str = " • ".join(f"`{c.get('label', c.get('channel'))}`" for c in channels[:5])
            embed.add_field(name="📡 Active Communion Channels", value=ch_str[:1024], inline=False)

        if not offers:
            embed.add_field(
                name=get_pact_ui_label("tab_discover", lang),
                value="*No Patron channels reachable at your current coordinates. Visit a Faction Vault, Crimson Auction, Campus Mystery spot, or weaken a sapient boss to ≤15% HP.*",
                inline=False,
            )
            return embed

        for off in offers[:6]:
            pid = str(off.get("patron_id") or "")
            marker = "👉 " if pid == selected_patron_id else ""
            app = off.get("appraisal") or {}
            app_state = str(app.get("state") or "neutral")
            sp = off.get("combat_skill") or {}
            f_util = off.get("field_utility") or {}
            locks_txt = _format_stat_locks(off.get("tier1_stat_locks"), float(off.get("tier1_max_hp_lock_pct") or 0.0))

            lines = [
                f"*“{app.get('quote', 'Name your price.')}”*",
                f"**Appraisal:** `{app_state.upper()}` (`{app.get('cost_mult', 1.0)}x`) • **Channel:** `{off.get('channel_label', '')}`",
                f"**0-MP Skill:** {sp.get('emoji', '🩸')} **{sp.get('name', 'Skill')}** — {sp.get('description', '')}",
                f"**Utility:** ✨ **{f_util.get('name', 'Passive')}** • **Locks:** `{locks_txt}`",
            ]
            if off.get("exclusive_tier3_holder"):
                lines.append(f"👑 **Tier III Held By:** `{off['exclusive_tier3_holder']}`")
            if not off.get("can_sign") and off.get("blocked_reason"):
                lines.append(f"🔒 **Blocked:** {off['blocked_reason']}")
            embed.add_field(
                name=f"{marker}{off.get('name', pid)} ({str(off.get('element', 'aether')).title()})"[:256],
                value="\n".join(lines)[:1024],
                inline=False,
            )
        return embed

    comp = list(overview.get("compendium") or [])
    if not comp:
        embed.add_field(
            name=get_pact_ui_label("tab_compendium", lang),
            value="*No Entity Patrons recorded in your account archive yet.*",
            inline=False,
        )
        return embed

    c_lines: List[str] = []
    for row in comp[:15]:
        t_rom = _ROMAN_TIERS.get(int(row.get("max_tier_reached") or 1), "I")
        status_tag = "🩸 Active" if row.get("is_currently_contracted") else "✅ Contracted"
        c_lines.append(
            f"**{row.get('display_name', row.get('patron_id'))}** (`{status_tag}` • Max Tier `{t_rom}` • Signed `{row.get('times_signed', 1)}x` • Invoked `{row.get('times_invoked', 0)}x`)"
        )
    embed.add_field(
        name=f"📖 {get_pact_ui_label('tab_compendium', lang)} ({len(comp)})",
        value="\n".join(c_lines)[:1024],
        inline=False,
    )
    return embed


class ContractPatronSelect(discord.ui.Select):
    """Dropdown selector for choosing an active covenant or available Patron offer."""

    def __init__(self, items: List[Dict[str, Any]], selected_id: Optional[str], placeholder: str):
        options: List[discord.SelectOption] = []
        for item in items[:25]:
            pid = str(item.get("patron_id") or "")
            if not pid:
                continue
            label = str(item.get("name") or pid)[:100]
            desc = str(item.get("title") or item.get("channel_label") or item.get("element") or "")[:100]
            options.append(
                discord.SelectOption(
                    label=label,
                    value=pid,
                    description=desc,
                    emoji="🩸",
                    default=(pid == selected_id),
                )
            )
        super().__init__(
            placeholder=placeholder[:100],
            min_values=1,
            max_values=1,
            options=options,
            row=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view: EntityContractsView = self.view  # type: ignore[assignment]
        view.selected_patron_id = self.values[0]
        view.selected_sign_tier = 1
        view._rebuild_components()
        embed = build_entity_contracts_embed(
            view.overview,
            tab=view.tab,
            selected_patron_id=view.selected_patron_id,
            lang=view.lang,
        )
        await interaction.response.edit_message(embed=embed, view=view)


class EntityContractsView(SessionRestrictedView):
    """Interactive Discord UI View providing 100% parity with `EntityContractsModal.jsx`."""

    def __init__(
        self,
        cog: Any,
        session_id: int,
        user_id: int,
        overview: Dict[str, Any],
        *,
        tab: str = "active",
        lang: str = "en",
    ):
        super().__init__(session_id=session_id, owner_user_id=user_id, timeout=240)
        self.cog = cog
        self.user_id = int(user_id)
        self.overview = overview
        self.tab = tab
        self.lang = lang
        self.selected_patron_id: Optional[str] = None
        self.selected_sign_tier: int = 1
        self._ensure_valid_selection()
        self._rebuild_components()

    def _ensure_valid_selection(self) -> None:
        pool = (
            list(self.overview.get("active_pacts") or [])
            if self.tab == "active"
            else list(self.overview.get("available_patrons") or [])
            if self.tab == "discover"
            else []
        )
        valid_ids = [str(x.get("patron_id")) for x in pool if x.get("patron_id")]
        if not valid_ids:
            self.selected_patron_id = None
        elif self.selected_patron_id not in valid_ids:
            self.selected_patron_id = valid_ids[0]

    def _rebuild_components(self) -> None:
        self.clear_items()

        # Row 0: Tab navigation buttons
        for tab_key, lbl_key, emoji in (
            ("active", "tab_active", "🩸"),
            ("discover", "tab_discover", "✨"),
            ("compendium", "tab_compendium", "📖"),
        ):
            btn = discord.ui.Button(
                label=get_pact_ui_label(lbl_key, self.lang)[:80],
                emoji=emoji,
                style=discord.ButtonStyle.danger if self.tab == tab_key else discord.ButtonStyle.secondary,
                row=0,
            )
            btn.callback = self._make_tab_callback(tab_key)
            self.add_item(btn)

        # Row 1 + Row 2: Context-sensitive select & ritual actions
        if self.tab == "active":
            pacts = list(self.overview.get("active_pacts") or [])
            if pacts:
                self.add_item(ContractPatronSelect(pacts, self.selected_patron_id, "Select active covenant..."))
                cur = next((p for p in pacts if str(p.get("patron_id")) == self.selected_patron_id), pacts[0])

                feed_btn = discord.ui.Button(
                    label=get_pact_ui_label("feed_btn", self.lang)[:80],
                    emoji="🕯️",
                    style=discord.ButtonStyle.success,
                    row=2,
                )
                feed_btn.callback = self._make_ritual_callback("feed", str(cur["patron_id"]))
                self.add_item(feed_btn)

                if int(cur.get("tier") or 1) < 3:
                    up_btn = discord.ui.Button(
                        label=f"{get_pact_ui_label('upgrade_btn', self.lang)} (Tier {_ROMAN_TIERS.get(int(cur.get('tier', 1)) + 1, 'II')})"[:80],
                        emoji="⬆️",
                        style=discord.ButtonStyle.primary,
                        disabled=not bool(cur.get("can_upgrade")),
                        row=2,
                    )
                    up_btn.callback = self._make_ritual_callback("upgrade", str(cur["patron_id"]), tier=int(cur.get("tier", 1)) + 1)
                    self.add_item(up_btn)

                peaceful = bool(cur.get("peaceful_scrub_available"))
                sev_lbl = (
                    f"{get_pact_ui_label('sever_scrub_btn', self.lang)} ({cur.get('scrub_credit_fee', 0)} Cr)"
                    if peaceful
                    else get_pact_ui_label("sever_exorcism_btn", self.lang)
                )
                sev_btn = discord.ui.Button(
                    label=sev_lbl[:80],
                    emoji="⚔️" if not peaceful else "⛩️",
                    style=discord.ButtonStyle.secondary if peaceful else discord.ButtonStyle.danger,
                    row=2,
                )
                sev_btn.callback = self._make_ritual_callback("sever", str(cur["patron_id"]))
                self.add_item(sev_btn)

        elif self.tab == "discover":
            offers = list(self.overview.get("available_patrons") or [])
            if offers:
                self.add_item(ContractPatronSelect(offers, self.selected_patron_id, "Select Patron to appraise or bind..."))
                cur_off = next((o for o in offers if str(o.get("patron_id")) == self.selected_patron_id), offers[0])
                upfront_cap = int((cur_off.get("appraisal") or {}).get("upfront_tier_cap") or 1)
                if cur_off.get("exclusive_tier3_holder") and upfront_cap >= 3:
                    upfront_cap = 2

                if upfront_cap > 1:
                    cycle_btn = discord.ui.Button(
                        label=f"Tier {_ROMAN_TIERS.get(self.selected_sign_tier, 'I')} (Favored)"[:80],
                        emoji="🌟",
                        style=discord.ButtonStyle.secondary,
                        row=2,
                    )
                    cycle_btn.callback = self._make_cycle_tier_callback(upfront_cap)
                    self.add_item(cycle_btn)

                sign_btn = discord.ui.Button(
                    label=get_pact_ui_label("sign_btn", self.lang)[:80],
                    emoji="🩸",
                    style=discord.ButtonStyle.danger,
                    disabled=not bool(cur_off.get("can_sign")),
                    row=2,
                )
                sign_btn.callback = self._make_ritual_callback("sign", str(cur_off["patron_id"]), tier=self.selected_sign_tier)
                self.add_item(sign_btn)

    def _make_tab_callback(self, next_tab: str):
        async def _cb(interaction: discord.Interaction) -> None:
            self.tab = next_tab
            self._ensure_valid_selection()
            self._rebuild_components()
            embed = build_entity_contracts_embed(
                self.overview,
                tab=self.tab,
                selected_patron_id=self.selected_patron_id,
                lang=self.lang,
            )
            await interaction.response.edit_message(embed=embed, view=self)

        return _cb

    def _make_cycle_tier_callback(self, max_tier: int):
        async def _cb(interaction: discord.Interaction) -> None:
            self.selected_sign_tier = (self.selected_sign_tier % max_tier) + 1
            self._rebuild_components()
            embed = build_entity_contracts_embed(
                self.overview,
                tab=self.tab,
                selected_patron_id=self.selected_patron_id,
                lang=self.lang,
            )
            await interaction.response.edit_message(embed=embed, view=self)

        return _cb

    def _make_ritual_callback(self, action: str, patron_id: str, *, tier: int = 1):
        async def _cb(interaction: discord.Interaction) -> None:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
            try:
                async with distributed_adventure_lock(self.user_id, self.session_id):
                    res = await adb(
                        execute_pact_ritual_action,
                        self.session_id,
                        self.user_id,
                        action,
                        patron_id,
                        tier=tier,
                        lang=self.lang,
                    )
            except ValueError as err:
                await interaction.followup.send(f"❌ {err}", ephemeral=True)
                return

            self.overview = res.get("overview") or await adb(
                build_contracts_overview_payload, self.session_id, self.user_id, lang=self.lang
            )
            if action == "sign":
                self.tab = "active"
                self.selected_patron_id = patron_id
            self._ensure_valid_selection()
            self._rebuild_components()
            embed = build_entity_contracts_embed(
                self.overview,
                tab=self.tab,
                selected_patron_id=self.selected_patron_id,
                lang=self.lang,
            )
            try:
                await interaction.edit_original_response(embed=embed, view=self)
            except discord.HTTPException:
                pass

            await interaction.followup.send(f"🩸 {res.get('message', 'Covenant updated.')}", ephemeral=True)
            if (res.get("spawned_exorcism_boss") or res.get("boss_surrender")) and self.cog is not None:
                fresh_session = await adb(db.get_session, self.session_id)
                if fresh_session:
                    await self.cog._resend_current_scene(interaction, fresh_session, use_followup=True)

        return _cb
