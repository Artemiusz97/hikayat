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

        session_id = char.get("active_session_id")
        if not session_id:
            await interaction.followup.send("❌ Your character is not currently in an adventure session.", ephemeral=True)
            return

        session = await adb(db.get_session, session_id)
        scen_key = session.get("scenario", "fantasy") if session else "fantasy"
        if not scenario_data.is_mechanic_enabled(scen_key, "faction_reputation"):
            await interaction.followup.send("❌ Faction mechanics are disabled for this scenario.", ephemeral=True)
            return

        factions = ensure_session_factions_seeded(session_id, scen_key)
        if not factions:
            await interaction.followup.send("📜 No factions discovered yet.", ephemeral=True)
            return

        # Show overview list by default, similar to /contacts
        embed = build_faction_list_embed(factions, char, scen_key)
        view = FactionsView(factions, char, scen_key, active_faction=None, user_id=interaction.user.id)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(FactionsCog(bot))
