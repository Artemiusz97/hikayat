from __future__ import annotations
"""
Discord Cog for viewing Faction Standings, Hierarchy, and Reputation.
"""
import discord
from discord import app_commands
from discord.ext import commands

import db
from db import adb
import scenario_data
from mechanics.social.factions import (
    get_faction_tier,
    get_active_perks,
    get_hierarchy,
    guess_hierarchy_template,
    ensure_session_factions_seeded
)


import re

def get_scenario_faction_title(scen_key: str) -> tuple[str, str]:
    from scenario_data import has_tag
    if has_tag(scen_key, "high_school") or has_tag(scen_key, "high_school_drama"):
        return ("🏫", "Campus Factions & Student Clubs")
    if has_tag(scen_key, "cyberpunk"):
        return ("🏢", "Megacorporations & Netrunner Syndicates")
    if has_tag(scen_key, "space") or has_tag(scen_key, "sci_fi"):
        return ("🚀", "Interstellar Factions & Star Corporations")
    if has_tag(scen_key, "steampunk"):
        return ("⚙️", "Engineering Guilds & Labor Unions")
    if has_tag(scen_key, "post_apocalypse") or has_tag(scen_key, "nuclear_post_apocalypse"):
        return ("📻", "Wasteland Factions & Survivor Bastions")
    if has_tag(scen_key, "dark_fantasy") or has_tag(scen_key, "grimdark"):
        return ("📜", "Orders, Cults & Dark Alliances")
    return ("🛡️", "Known Factions & Guilds")


def get_faction_emoji(name: str, category: str = "", template: str = "") -> str:
    """Return a thematic dynamic emoji based on faction name, category, and template."""
    n = (name or "").lower()
    c = (category or "").lower()
    t = (template or "").lower()

    # Specific school clubs & sub-genres
    if any(k in n for k in ("esport", "gaming", "game", "arcade", "video game")): return "🎮"
    if any(k in n for k in ("journalism", "newspaper", "press", "media", "broadcast")): return "📰"
    if any(k in n for k in ("cook", "culinary", "baking", "food", "chef")): return "🍳"
    if any(k in n for k in ("astronomy", "stargazing", "telescope", "space")): return "🔭"
    if any(k in n for k in ("drama", "theat", "acting", "stage")): return "🎭"
    # Inquisition / Witch Hunters
    if any(k in n for k in ("inquisit", "witch hunter", "witch-hunter", "purifier", "cleansing flame")): return "🔥"

    # Cults / Occult Covens
    if re.search(r'\bcults?\b', n) or any(k in n for k in ("coven", "blood pact", "necroman", "eldritch", "harbinger")): return "👁️"

    if any(k in n for k in ("occult", "mystery", "supernatural", "paranormal", "arcane", "mystic", "sorcer")): return "🔮"
    if any(k in n for k in ("council", "stuco", "senate", "presidency", "governing")): return "🏛️"
    if any(k in n for k in ("disciplin", "prefect", "monitor", "morals", "police", "guard", "warden")): return "⚖️"
    if any(k in n for k in ("lover", "romance", "velvet", "secret", "allure", "siren", "desire", "passion", "pleasure", "kiss", "aphrodite")): return "🌹"
    if any(k in n for k in ("music", "band", "orchestra", "idol", "choir", "sound", "harmony")): return "🎵"
    if any(k in n for k in ("sport", "kendo", "martial", "box", "athlet", "swim", "track", "bask", "socc", "judo", "karate")): return "🥋"
    if re.search(r'\b(art|arts|manga|anime|drawing|painting)\b', n): return "🎨"
    if any(k in n for k in ("book", "literat", "library", "read", "athenaeum")): return "📚"
    if any(k in n for k in ("alchem", "apothecary", "potion", "distill", "elixir", "transmutation")): return "⚗️"
    if any(k in n for k in ("science", "chem", "biolog", "physics", "lab", "astro", "research", "robotics", "tech")): return "🧪"

    # Merchant & Trade
    if any(k in n for k in ("merchant", "caravan", "bourse", "banking house", "trade league", "coin league")): return "🪙"

    # Scavengers & Wasteland Scrap
    if any(k in n for k in ("scavenger", "salvage", "scrapper", "junkers", "scrap crew", "waste reclaimer")): return "🔧"

    # Delinquents, gangs, raiders
    if any(k in n for k in ("delinquent", "brawler", "yanki", "gang", "viper", "dragon", "skull", "wolf", "wolves", "rebel", "thug", "hoodlum", "crew", "pack", "fangs", "stormborn")): return "🐺"
    if any(k in n for k in ("raider", "marauder", "vulture", "mutant", "rust", "wasteland")): return "💀"

    # Cyberpunk / Sci-Fi
    if any(k in n for k in ("netrunner", "hacker", "ghostnet", "subnet", "cipher", "glitch", "zero-day", "darkgrid", "matrix")): return "🌐"
    if any(k in n for k in ("corp", "megacorp", "industries", "systems", "dynamics", "nanotech", "biotech", "cybernetics", "arasaka", "militech", "synthetix", "apex", "nexus", "omnicorp")): return "🏢"
    if any(k in n for k in ("fleet", "navy", "orbit", "solar", "stellar", "galaxy", "interstellar", "starship", "void", "space", "aeronaut", "dirigible", "airship", "flotilla")):
        return "🚀" if any(k in n for k in ("orbit", "star", "space", "galaxy", "solar", "interstellar", "void")) else "🚢"

    # Steampunk
    if any(k in n for k in ("clockwork", "mechanist", "aether", "steam", "brass", "boiler", "cog", "foundry")): return "⚙️"
    if any(k in n for k in ("union", "syndicalist", "metalworkers", "smelters", "labor", "miners", "prospectors", "boilermakers")): return "⚒️"

    # Fantasy / Orders / Guilds
    if any(k in n for k in ("knight", "paladin", "templar", "crusade", "holy", "radiant", "sunlit", "shield", "aegis", "chivalric")): return "⚔️"
    if any(k in n for k in ("adventur", "mercenary", "explorer", "scout", "ranger", "hunter", "bounty")): return "🧭"
    if any(k in n for k in ("settlement", "bastion", "haven", "sanctuary", "refuge", "oasis", "colony")): return "🏕️"

    # Category / template fallbacks
    if t == "council" or c == "council": return "🏛️"
    if t == "discipline" or c == "discipline": return "⚖️"
    if t == "club" or c == "club": return "🏫"
    if t == "delinquents" or c == "delinquents": return "🐺"
    if t == "corpo" or c == "corpo": return "🏢"
    if t == "syndicate" or c == "syndicate": return "🌐"
    if t == "order" or c == "order": return "⚔️"
    if t == "settlement" or c == "settlement": return "🏕️"
    if t == "alchemy" or c == "alchemy": return "⚗️"
    if t == "academy" or c == "academy": return "📜"
    if t == "union" or c == "union": return "⚒️"
    if t == "fleet" or c == "fleet": return "🚢"
    if t == "merchant" or c == "merchant": return "🪙"
    if t == "inquisition" or c == "inquisition": return "🔥"
    if t == "cult" or c == "cult": return "👁️"
    if t == "scavenger" or c == "scavenger": return "🔧"
    if t == "guild" or c == "guild": return "🧭"

    return "🛡️"


class FactionSelect(discord.ui.Select):
    def __init__(self, page_factions: list[dict], all_factions: list[dict], char: dict, scenario_key: str,
                 page: int = 0, total_pages: int = 1):
        self.all_factions = all_factions
        self.char = char
        self.scenario_key = scenario_key
        self.page = page
        self.factions_dict = {f["faction_id"]: f for f in all_factions}

        options = []
        for f in page_factions:
            score = f.get("reputation_score", 0)
            tier = get_faction_tier(score)
            is_member = (char.get("joined_faction_id") == f["faction_id"])
            mark = "⭐ " if is_member else ""
            membership_status = f"Member (Rank {char.get('faction_rank', 1)})" if is_member else "Non-member"
            emoji = get_faction_emoji(f["name"], f.get("category", ""), f.get("hierarchy_template", ""))
            options.append(discord.SelectOption(
                label=f"{mark}{f['name'][:90]}",
                emoji=emoji,
                description=f"Standing: {tier['name']} ({score:+d}) | {membership_status}"[:100],
                value=f["faction_id"]
            ))

        placeholder = f"Select a faction (Page {page + 1}/{total_pages})..." if total_pages > 1 else "Select a faction to view details..."
        super().__init__(placeholder=placeholder, min_values=1, max_values=1, options=options, row=0)

    async def callback(self, interaction: discord.Interaction):
        faction_id = self.values[0]
        faction = self.factions_dict.get(faction_id)
        if not faction:
            await interaction.response.send_message("Faction not found.", ephemeral=True)
            return

        embed = build_faction_detail_embed(faction, self.char)
        new_view = FactionsView(self.all_factions, self.char, self.scenario_key, active_faction=faction, page=self.page, user_id=interaction.user.id)
        await interaction.response.edit_message(embed=embed, view=new_view)


class BackToOverviewButton(discord.ui.Button):
    def __init__(self, all_factions: list[dict], char: dict, scenario_key: str, page: int = 0):
        super().__init__(label="Back to Overview", emoji="🔙", style=discord.ButtonStyle.primary, row=1)
        self.all_factions = all_factions
        self.char = char
        self.scenario_key = scenario_key
        self.page = page

    async def callback(self, interaction: discord.Interaction):
        embed = build_faction_list_embed(self.all_factions, self.char, self.scenario_key)
        new_view = FactionsView(self.all_factions, self.char, self.scenario_key, active_faction=None, page=self.page, user_id=interaction.user.id)
        await interaction.response.edit_message(embed=embed, view=new_view)


class FactionsView(discord.ui.View):
    def __init__(self, factions: list[dict], char: dict, scenario_key: str,
                 active_faction: dict | None = None, page: int = 0, user_id: int | None = None):
        super().__init__(timeout=300)
        self.factions = factions
        self.char = char
        self.scenario_key = scenario_key
        self.active_faction = active_faction
        self.page = page
        self.user_id = user_id or char.get("user_id", 0)
        self.page_size = 25
        self.total_pages = max(1, (len(factions) + self.page_size - 1) // self.page_size)

        start = self.page * self.page_size
        end = start + self.page_size
        current_page_factions = factions[start:end]

        self.add_item(FactionSelect(current_page_factions, factions, char, scenario_key, page=self.page, total_pages=self.total_pages))

        if self.active_faction:
            self.add_item(BackToOverviewButton(factions, char, scenario_key, page=self.page))

        if self.total_pages > 1:
            row_idx = 2 if self.active_faction else 1
            prev_btn = discord.ui.Button(label="◀️ Prev", style=discord.ButtonStyle.secondary, disabled=(self.page == 0), row=row_idx)
            prev_btn.callback = self._on_prev
            self.add_item(prev_btn)

            page_label = discord.ui.Button(label=f"Page {self.page + 1}/{self.total_pages} ({len(factions)} total)", style=discord.ButtonStyle.secondary, disabled=True, row=row_idx)
            self.add_item(page_label)

            next_btn = discord.ui.Button(label="Next ▶️", style=discord.ButtonStyle.secondary, disabled=(self.page >= self.total_pages - 1), row=row_idx)
            next_btn.callback = self._on_next
            self.add_item(next_btn)

    async def _on_prev(self, interaction: discord.Interaction):
        new_page = max(0, self.page - 1)
        if self.active_faction:
            embed = build_faction_detail_embed(self.active_faction, self.char)
        else:
            embed = build_faction_list_embed(self.factions, self.char, self.scenario_key)
        new_view = FactionsView(self.factions, self.char, self.scenario_key, active_faction=self.active_faction, page=new_page, user_id=self.user_id)
        await interaction.response.edit_message(embed=embed, view=new_view)

    async def _on_next(self, interaction: discord.Interaction):
        new_page = min(self.total_pages - 1, self.page + 1)
        if self.active_faction:
            embed = build_faction_detail_embed(self.active_faction, self.char)
        else:
            embed = build_faction_list_embed(self.factions, self.char, self.scenario_key)
        new_view = FactionsView(self.factions, self.char, self.scenario_key, active_faction=self.active_faction, page=new_page, user_id=self.user_id)
        await interaction.response.edit_message(embed=embed, view=new_view)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.user_id and interaction.user.id != self.user_id:
            await interaction.response.send_message("This faction view is for another player.", ephemeral=True)
            return False
        return True


def build_faction_list_embed(factions: list[dict], char: dict, scenario_key: str) -> discord.Embed:
    icon, title = get_scenario_faction_title(scenario_key)
    char_name = char.get("name", "Adventurer")

    embed = discord.Embed(
        title=f"{icon} {title}",
        description=f"Faction standings and reputations for **{char_name}**.",
        color=discord.Color.blue()
    )

    if not factions:
        embed.add_field(
            name="No Factions Known",
            value="You haven't discovered any factions yet in this region.",
            inline=False
        )
        return embed

    for f in factions[:15]:
        score = f.get("reputation_score", 0)
        tier = get_faction_tier(score)
        is_member = (char.get("joined_faction_id") == f["faction_id"])
        player_rank = char.get("faction_rank", 0) if is_member else 0
        membership_str = f"Rank {player_rank}: {char.get('faction_title', 'Member')}" if is_member else "Not a member"
        
        emoji = get_faction_emoji(f["name"], f.get("category", ""), f.get("hierarchy_template", ""))
        status_line = f"Standing: **{tier['name']}** (`{score:+d}`) | Membership: **{membership_str}**"

        embed.add_field(
            name=f"{emoji} {f['name']}",
            value=status_line,
            inline=False
        )

    embed.set_footer(text=f"Total Factions: {len(factions)} | Use the menu below to view full details")
    return embed


def build_faction_detail_embed(faction: dict, char: dict) -> discord.Embed:
    score = faction.get("reputation_score", 0)
    tier = get_faction_tier(score)
    is_member = (char.get("joined_faction_id") == faction["faction_id"])
    player_rank = char.get("faction_rank", 0) if is_member else 0
    emoji = get_faction_emoji(faction["name"], faction.get("category", ""), faction.get("hierarchy_template", ""))
    
    embed = discord.Embed(title=f"{emoji} {faction['name']}", color=discord.Color.gold() if is_member else discord.Color.blue())
    embed.add_field(name="Standing", value=f"**{tier['name']}** (`{score:+d}`)", inline=True)
    
    if is_member:
        embed.add_field(name="Membership", value=f"Rank {player_rank}: {char.get('faction_title', 'Member')}", inline=True)
    else:
        embed.add_field(name="Membership", value="Not a member", inline=True)
        
    hq = faction.get("hq_location_id")
    if hq:
        embed.add_field(name="Headquarters", value=hq, inline=True)
        
    notes = faction.get("notes")
    if notes:
        embed.description = f"*{notes}*"
        
    perks = get_active_perks(faction, player_rank, score)
    if perks:
        embed.add_field(name="Active Perks", value="\n".join(f"• {p}" for p in perks), inline=False)
        
    # Roster
    roster = faction.get("leadership_roster")
    if roster:
        # Sort by rank descending
        sorted_roster = sorted(roster, key=lambda x: x.get("rank", 0), reverse=True)
        roster_lines = []
        for r in sorted_roster:
            mark = " `[👤 (You)]`" if r.get("is_player") else ""
            roster_lines.append(f"**{r.get('title', 'Rank')}** — {r.get('name', 'Unknown')}{mark}")
        if roster_lines:
            embed.add_field(name="Hierarchy & Roster", value="\n".join(roster_lines), inline=False)
    else:
        embed.add_field(name="Hierarchy", value="*Roster not yet encountered.*", inline=False)
        
    return embed


class FactionsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="factions", description="View interactive faction standings, hierarchy, and rosters.")
    async def factions(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        char = await adb(db.get_character, interaction.user.id)
        if not char:
            await interaction.followup.send("❌ You have no active character. Create one with `/character create`.", ephemeral=True)
            return

        session_id = char.get("active_session_id") or (await adb(db.get_active_session_id_for_user, interaction.user.id))
        if not session_id:
            await interaction.followup.send("❌ Your character is not currently in an adventure session.", ephemeral=True)
            return

        session = await adb(db.get_session, session_id)
        scen_key = session.get("scenario", "fantasy") if session else "fantasy"
        if not scenario_data.is_mechanic_enabled(scen_key, "faction_reputation"):
            await interaction.followup.send("❌ Faction mechanics are disabled for this scenario.", ephemeral=True)
            return

        factions = await adb(ensure_session_factions_seeded, session_id, scen_key)
        if not factions:
            await interaction.followup.send("📜 No factions discovered yet.", ephemeral=True)
            return

        # Show overview list by default, similar to /contacts
        embed = build_faction_list_embed(factions, char, scen_key)
        view = FactionsView(factions, char, scen_key, active_faction=None, user_id=interaction.user.id)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="encyclopedia", description="View the Anomaly & Folklore Encyclopedia, Codex progress, and Containment Vault log.")
    async def encyclopedia(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        char = await adb(db.get_character, interaction.user.id)
        session_id = (char.get("active_session_id") if char else None) or (await adb(db.get_active_session_id_for_user, interaction.user.id))
        effective_sid = session_id
        if session_id:
            session = await adb(db.get_session, session_id)
            scen_key = str((session or {}).get("scenario") or "fantasy")
            if not scenario_data.is_anomalous_incursions_scenario(scen_key):
                effective_sid = None

        from mechanics.world.folklore_codex import build_encyclopedia_payload

        payload = await adb(build_encyclopedia_payload, effective_sid, interaction.user.id)
        view = EncyclopediaView(payload=payload, user_id=interaction.user.id)
        embed = view.build_embed()
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)


class EncyclopediaTraditionSelect(discord.ui.Select):
    def __init__(self, traditions: list[dict], current_tradition: str):
        options = [
            discord.SelectOption(
                label="All Cultural Traditions",
                value="all",
                emoji="🌍",
                default=(current_tradition == "all"),
            )
        ]
        for tr in traditions[:24]:
            key = str(tr.get("key") or "")
            lbl = str(tr.get("label") or key)[:80]
            disc = int(tr.get("discovered", 0) or 0)
            tot = int(tr.get("total", 0) or 0)
            options.append(
                discord.SelectOption(
                    label=lbl,
                    value=key,
                    description=f"Discovered: {disc}/{tot}",
                    emoji="📜",
                    default=(current_tradition == key),
                )
            )
        super().__init__(placeholder="Filter by Folklore Tradition...", min_values=1, max_values=1, options=options, row=0)

    async def callback(self, interaction: discord.Interaction):
        view: EncyclopediaView = self.view  # type: ignore[assignment]
        if interaction.user.id != view.user_id:
            await interaction.response.send_message("This menu belongs to another player.", ephemeral=True)
            return
        view.tradition = self.values[0]
        view.page = 0
        view.refresh_items()
        await interaction.response.edit_message(embed=view.build_embed(), view=view)


class EncyclopediaEntrySelect(discord.ui.Select):
    def __init__(self, entries: list[dict], user_id: int):
        self.entries_by_id = {str(e.get("codex_id")): e for e in entries if e.get("codex_id")}
        self.user_id = user_id
        options = [
            discord.SelectOption(
                label=str(e.get("name") or "Unknown")[:100],
                value=str(e.get("codex_id")),
                description=str(e.get("subtitle") or e.get("tradition") or "")[:100],
                emoji="📜" if e.get("unlock_stage") == "contained" else "🔍",
            )
            for e in entries
            if e.get("codex_id")
        ][:25]
        if not options:
            options = [discord.SelectOption(label="No Discoveries", value="__none__", description="No entries available")]
        super().__init__(
            placeholder="🔍 Inspect Folklore Record Details...",
            options=options,
            row=3,
        )

    async def callback(self, inter: discord.Interaction):
        if inter.user.id != self.user_id:
            await inter.response.send_message("This menu belongs to another player.", ephemeral=True)
            return
        if not self.values or self.values[0] == "__none__":
            await inter.response.send_message("No folklore record selected.", ephemeral=True)
            return
        entry = self.entries_by_id.get(self.values[0])
        if not entry:
            await inter.response.send_message("Record not found.", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"📜 {entry.get('name', 'Anomalous Record')}",
            description=f"*{entry.get('subtitle') or entry.get('tradition', 'Global Folklore')}*",
            color=0x9B59B6,
        )
        if entry.get("lore_summary"):
            embed.add_field(name="📖 Folklore Lore", value=entry["lore_summary"][:1024], inline=False)
        if entry.get("taboo_rule"):
            embed.add_field(name="⚠️ Taboo Rule", value=f"```yaml\n{str(entry['taboo_rule'])[:1008]}\n```", inline=False)
        if entry.get("containment_protocol"):
            embed.add_field(name="🛡️ Containment Protocol", value=entry["containment_protocol"][:1024], inline=False)
        if entry.get("tether_vessel"):
            embed.add_field(name="🪢 Vessel Tether", value=str(entry["tether_vessel"])[:1024], inline=True)
        if entry.get("weaknesses"):
            weaks = ", ".join(entry["weaknesses"]) if isinstance(entry["weaknesses"], list) else str(entry["weaknesses"])
            embed.add_field(name="🎯 Known Weaknesses", value=weaks[:1024], inline=True)
        if entry.get("relic_gear_name"):
            embed.add_field(name="⚔️ Secured Relic", value=str(entry["relic_gear_name"])[:1024], inline=True)

        stage = str(entry.get("unlock_stage") or "sighted").title()
        embed.set_footer(text=f"Codex ID: {entry.get('codex_id')} | Research Status: {stage}")
        await inter.response.send_message(embed=embed, ephemeral=True)


class EncyclopediaView(discord.ui.View):
    PAGE_SIZE = 8

    def __init__(self, payload: dict, user_id: int):
        super().__init__(timeout=300)
        self.payload = payload or {}
        self.user_id = user_id
        self.mode = "folklore"  # "folklore" | "field_log"
        self.tradition = "all"
        self.page = 0
        self.refresh_items()

    def _filtered_entries(self) -> list[dict]:
        entries = list(self.payload.get("folklore_codex") or [])
        if self.tradition != "all":
            entries = [e for e in entries if e.get("tradition_key") == self.tradition or e.get("tradition") == self.tradition]
        return entries

    def refresh_items(self) -> None:
        self.clear_items()
        if self.mode == "folklore":
            traditions = list(self.payload.get("traditions") or [])
            if traditions:
                self.add_item(EncyclopediaTraditionSelect(traditions, self.tradition))

        codex_btn = discord.ui.Button(
            label=f"Folklore Codex [{self.payload.get('discovered_count', 0)}/{self.payload.get('total_folklore_count', 50)}]",
            emoji="📜",
            style=discord.ButtonStyle.primary if self.mode == "folklore" else discord.ButtonStyle.secondary,
            row=1,
        )
        vault_count = len(self.payload.get("field_log") or []) + len(self.payload.get("vault_log") or [])
        vault_btn = discord.ui.Button(
            label=f"Field Log & Vault [{vault_count}]",
            emoji="🔒",
            style=discord.ButtonStyle.primary if self.mode == "field_log" else discord.ButtonStyle.secondary,
            row=1,
        )

        async def _switch_folklore(inter: discord.Interaction):
            if inter.user.id != self.user_id:
                await inter.response.send_message("This menu belongs to another player.", ephemeral=True)
                return
            self.mode = "folklore"
            self.page = 0
            self.refresh_items()
            await inter.response.edit_message(embed=self.build_embed(), view=self)

        async def _switch_vault(inter: discord.Interaction):
            if inter.user.id != self.user_id:
                await inter.response.send_message("This menu belongs to another player.", ephemeral=True)
                return
            self.mode = "field_log"
            self.page = 0
            self.refresh_items()
            await inter.response.edit_message(embed=self.build_embed(), view=self)

        codex_btn.callback = _switch_folklore
        vault_btn.callback = _switch_vault
        self.add_item(codex_btn)
        self.add_item(vault_btn)

        total_items = (
            len(self._filtered_entries())
            if self.mode == "folklore"
            else max(1, len(self.payload.get("field_log") or []), len(self.payload.get("vault_log") or []))
        )
        max_page = max(0, (total_items - 1) // self.PAGE_SIZE)
        if max_page > 0:
            prev_btn = discord.ui.Button(label="◀ Prev", style=discord.ButtonStyle.secondary, disabled=(self.page <= 0), row=2)
            next_btn = discord.ui.Button(label="Next ▶", style=discord.ButtonStyle.secondary, disabled=(self.page >= max_page), row=2)

            async def _prev(inter: discord.Interaction):
                if inter.user.id != self.user_id:
                    await inter.response.send_message("This menu belongs to another player.", ephemeral=True)
                    return
                self.page = max(0, self.page - 1)
                self.refresh_items()
                await inter.response.edit_message(embed=self.build_embed(), view=self)

            async def _next(inter: discord.Interaction):
                if inter.user.id != self.user_id:
                    await inter.response.send_message("This menu belongs to another player.", ephemeral=True)
                    return
                self.page = min(max_page, self.page + 1)
                self.refresh_items()
                await inter.response.edit_message(embed=self.build_embed(), view=self)

            prev_btn.callback = _prev
            next_btn.callback = _next
            self.add_item(prev_btn)
            self.add_item(next_btn)

        if self.mode == "folklore":
            all_entries = self._filtered_entries()
            start = self.page * self.PAGE_SIZE
            page_entries = all_entries[start : start + self.PAGE_SIZE]
            discovered_entries = [e for e in page_entries if e.get("unlock_stage") != "undiscovered" and e.get("codex_id")]
            if discovered_entries:
                self.add_item(EncyclopediaEntrySelect(discovered_entries, self.user_id))

    def build_embed(self) -> discord.Embed:
        disc = int(self.payload.get("discovered_count", 0) or 0)
        ver = int(self.payload.get("verified_count", 0) or 0)
        cont = int(self.payload.get("contained_count", 0) or 0)
        tot = int(self.payload.get("total_folklore_count", 50) or 50)

        if self.mode == "field_log":
            embed = discord.Embed(
                title="🔒 Session Field Log & Containment Vault",
                description="Campaign-specific sightings, unmasked anomalies, and sealed Containment Vault captures.",
                color=discord.Color.teal(),
            )
            vault_log = list(self.payload.get("vault_log") or [])
            start = self.page * self.PAGE_SIZE
            v_chunk = vault_log[start : start + self.PAGE_SIZE]
            if v_chunk:
                v_lines = [
                    f"• **{v.get('entity_name') or v.get('name', 'Anomaly')}** — `{v.get('resolution_method') or v.get('resolution_mode') or 'Vaulted'}`"
                    for v in v_chunk
                ]
                embed.add_field(name=f"Containment Vault ({len(vault_log)})", value="\n".join(v_lines)[:1020], inline=False)
            elif not vault_log:
                embed.add_field(name="Containment Vault", value="*No anomalies sealed in this session yet.*", inline=False)

            f_log = list(self.payload.get("field_log") or [])
            chunk = f_log[start : start + self.PAGE_SIZE]
            if chunk:
                f_lines = []
                for item in chunk:
                    nm = item.get("public_name") if item.get("is_disguised") else (item.get("name") or "Unknown Anomaly")
                    st = str(item.get("status") or "sighted").upper()
                    tag = " `[Folklore]`" if (item.get("codex_id") and not item.get("is_disguised")) else ""
                    f_lines.append(f"• **{nm}**{tag} — `{st}`")
                embed.add_field(name=f"Session Field Sightings ({len(f_log)})", value="\n".join(f_lines)[:1020], inline=False)
            else:
                embed.add_field(name="Session Field Sightings", value="*No field sightings logged yet.*", inline=False)
            return embed

        entries = self._filtered_entries()
        max_page = max(1, (len(entries) + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        start = self.page * self.PAGE_SIZE
        chunk = entries[start : start + self.PAGE_SIZE]

        embed = discord.Embed(
            title=f"📜 Global Folklore Codex [{disc}/{tot}]",
            description=(
                f"👁️ **Sighted:** `{disc}` | 🛡️ **Verified:** `{ver}` | 🔒 **Contained:** `{cont}`\n"
                f"*Verified & Contained entries grant **Folklore Recognition (-1 Stage 1 Clue)** across future runs.*"
            ),
            color=discord.Color.gold(),
        )
        lines = []
        for e in chunk:
            st = str(e.get("unlock_stage") or "undiscovered")
            if st == "undiscovered":
                hint = str(e.get("hint") or "Unknown habitat")
                lines.append(f"🔒 **`???`** *({e.get('tradition_label', 'Folklore')})* — {hint}")
            else:
                icon = "🔒" if st == "contained" else ("🛡️" if st == "verified" else "👁️")
                rec = " `🧠 -1 Clue`" if e.get("folklore_recognition_active") else ""
                sub = f" — *{e.get('subtitle')}*" if e.get("subtitle") else ""
                line = f"{icon} **{e.get('name')}**{sub} `[{st.upper()}]`{rec}"
                if st in ("verified", "contained") and e.get("taboo_name"):
                    line += f"\n   ↳ ⚠️ *Taboo: {e.get('taboo_name')}* | Elem: `{str(e.get('primary_element', '')).upper()}`"
                elif e.get("sensory_omen"):
                    omen_short = str(e.get("sensory_omen"))[:95]
                    line += f"\n   ↳ *{omen_short}...*"
                lines.append(line)

        embed.add_field(
            name=f"Entries (Page {self.page + 1}/{max_page})",
            value="\n".join(lines)[:1020] if lines else "*No entries match filter.*",
            inline=False,
        )
        return embed


async def setup(bot: commands.Bot):
    await bot.add_cog(FactionsCog(bot))
