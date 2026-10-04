import discord
from discord import app_commands
from discord.ext import commands

import db
from db import adb
import game_engine
from character_data import (CUSTOM_CLASS_STARTING_ITEMS, POINT_BUY_POOL,
                             BASE_STAT_VALUE, MAX_STAT_VALUE, STATS, STAT_NAMES, STAT_EMOJI,
                             STAT_EFFECTS, STARTING_GOLD, EQUIPMENT_SLOTS, EQUIPMENT_SLOT_EMOJI,
                             DEFAULT_EQUIP_SLOT_FOR_ITEM_TYPE, GENDER_OPTIONS,
                             get_class_templates, get_all_class_templates, get_starting_weapons, get_all_starting_weapons,
                             get_starter_gear_by_class, get_starting_items, inventory_capacity, get_item_icon)
from scenario_data import load_scenarios, get_scenario


def build_character_sheet_embed(char: dict, equipment: dict, title_prefix: str = "") -> discord.Embed:
    from mechanics.social.races import format_race_display
    title = f"{title_prefix}{char['name']}"
    if char.get('char_class') and char['char_class'] != 'Adventurer':
        title += f" the {char['char_class']}"
    elif char.get('char_class'):
        title += f" ({char['char_class']})"

    embed = discord.Embed(
        title=title,
        description=char.get("class_description") or None,
        color=discord.Color.blurple()
    )
    days_adv = char.get("days_adventured") or 1
    xp_line = f"Level {char['level']}  |  {char['xp']} XP  |  ⏳ {days_adv} Day{'s' if days_adv != 1 else ''} Adventured"
    if char.get("pending_stat_points"):
        xp_line += f"  |  🌟 {char['pending_stat_points']} unspent stat point(s) — use `/allocate`"
    embed.add_field(name="Level / XP", value=xp_line, inline=False)
    scen_key = char.get("scenario", "fantasy")
    scen_name = load_scenarios().get(scen_key, {}).get("name", scen_key)
    identity_line = f"Scenario: **{scen_name}**"
    if char.get("race"):
        identity_line += f"  |  Race: **{format_race_display(char['race'])}**"
    if char.get("gender"):
        identity_line += f"  |  Gender: **{char['gender']}**"
    embed.add_field(name="Identity", value=identity_line, inline=False)
    embed.add_field(name="Stats",
                     value=(f"STR {char['str_']} | PER {char['per_']} | END {char['end_']} | CHA {char['cha']}\n"
                            f"INT {char['int_']} | AGI {char['agi']} | LUK {char['luk']}"),
                     inline=False)
    hp_str = f"❤️ {char['hp']}/{char['max_hp']}"
    if char.get("temp_hp"):
        hp_str += f" (🛡️ +{char['temp_hp']})"
    embed.add_field(name="Vitals",
                     value=f"{hp_str}  |  💙 {char['mp']}/{char['max_mp']}  |  🪙 {char['gold']} Gold",
                     inline=False)

    from scenario_data import is_non_combat_scenario
    char_scen = char.get("scenario", "fantasy")
    if is_non_combat_scenario(char_scen):
        embed.add_field(
            name="🎭 Scenario Mode",
            value="**Non-Combat (Slice of Life / Drama)**\n*Combat encounters & combat attributes are disabled. Equipment serves as cosmetics & narrative flair.*",
            inline=False
        )
    else:
        from mechanics.social.attributes import calculate_combat_attributes, format_combat_attributes_text
        equipped_list = [item for item in equipment.values() if item] if equipment else None
        attrs = calculate_combat_attributes(char, equipped_list, scenario=char_scen)
        embed.add_field(name="⚔️ Combat Attributes", value=format_combat_attributes_text(attrs), inline=False)

    from mechanics.combat.equipment import is_two_handed
    weapon_item = equipment.get("Weapon") if equipment else None
    weapon_is_2h = is_two_handed(weapon_item) if weapon_item else False
    has_armor = bool(equipment.get("Armor")) if equipment else False

    equip_lines = []
    has_any_equip = False
    for slot in EQUIPMENT_SLOTS:
        item = equipment.get(slot)
        slot_emoji = EQUIPMENT_SLOT_EMOJI.get(slot, '')
        if item:
            has_any_equip = True
            icon = get_item_icon(item["name"], item.get("item_type", ""), item.get("effect", ""), slot)
            dormant_str = " *(dormant)*" if (has_armor and slot in ("Top", "Bottom")) else ""
            equip_lines.append(f"{slot_emoji} **{slot}:** {icon} {item['name']}{dormant_str}")
        elif slot == "Shield" and weapon_is_2h:
            equip_lines.append(f"{slot_emoji} **{slot}:** *(unavailable)*")
        else:
            equip_lines.append(f"{slot_emoji} **{slot}:** *(empty)*")

    if not has_any_equip:
        embed.add_field(name="Equipment", value="*Ready for adventure — class and gear loadout will be chosen on adventure start!*", inline=False)
    else:
        embed.add_field(name="Equipment", value="\n".join(equip_lines), inline=False)

    if not is_non_combat_scenario(char_scen):
        known_sids = db.get_learned_spells(char.get("user_id", 0))
        if known_sids:
            from mechanics.combat.spells import get_spell
            s_tags = []
            for sid in known_sids:
                sp = get_spell(sid)
                if sp:
                    s_tags.append(f"{sp.get('emoji', '🔮')} **{sp['name']}** *({sp.get('tier_name', 'Basic')})*")
            if s_tags:
                embed.add_field(name="🔮 Known Spells", value=" • ".join(s_tags), inline=False)

    embed.add_field(name="Status Effects", value=char.get("status_effects") or "None", inline=False)
    embed.set_footer(text="Use /inventory show to view your full inventory.")
    return embed


class StatAllocationView(discord.ui.View):
    """Interactive point-buy stat allocator used during character creation --
    the final step, after gender and race have been picked.
    """

    def __init__(self, user_id: int, name: str, gender: str,
                 race: str = "human", race_description: str = "", scenario: str = "fantasy"):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.name = name
        self.gender = gender
        self.race = race
        self.race_description = race_description
        self.scenario = scenario
        self.values = {s: BASE_STAT_VALUE for s in STATS}
        self.selected_stat = STATS[0]
        self._rebuild()

    @property
    def points_spent(self) -> int:
        return sum(self.values.values()) - BASE_STAT_VALUE * len(STATS)

    @property
    def points_remaining(self) -> int:
        return POINT_BUY_POOL - self.points_spent

    def _rebuild(self):
        self.clear_items()

        options = []
        for s in STATS:
            val = self.values[s]
            suffix = " (MAX)" if val >= MAX_STAT_VALUE else ""
            options.append(discord.SelectOption(
                label=f"{STAT_NAMES[s]} ({s}) — currently {val}{suffix}",
                value=s,
                emoji=STAT_EMOJI.get(s),
                default=(s == self.selected_stat),
            ))
        select = discord.ui.Select(placeholder="Choose a stat to adjust...", options=options, row=0)
        select.callback = self._on_select
        self.add_item(select)

        at_base = self.values[self.selected_stat] <= BASE_STAT_VALUE
        at_cap = self.values[self.selected_stat] >= MAX_STAT_VALUE

        minus = discord.ui.Button(label="-1", emoji="➖", style=discord.ButtonStyle.secondary,
                                   row=1, disabled=at_base)
        minus.callback = self._on_minus
        self.add_item(minus)

        plus = discord.ui.Button(label="+1", emoji="➕", style=discord.ButtonStyle.primary,
                                  row=1, disabled=(at_cap or self.points_remaining <= 0))
        plus.callback = self._on_plus
        self.add_item(plus)

        reset = discord.ui.Button(label="Reset", emoji="↩️", style=discord.ButtonStyle.secondary, row=1)
        reset.callback = self._on_reset
        self.add_item(reset)

        confirm = discord.ui.Button(label="Confirm & Create Character", emoji="✅",
                                     style=discord.ButtonStyle.success, row=2)
        confirm.callback = self._on_confirm
        self.add_item(confirm)

    def build_embed(self) -> discord.Embed:
        from mechanics.social.races import format_race_display
        embed = discord.Embed(
            title=f"Allocate Stats — {self.name}",
            description="Invest your bonus points across your base attributes. Any points left unspent are saved -- use `/allocate` any time to spend them later.",
            color=discord.Color.gold(),
        )
        lines = []
        for s in STATS:
            pointer = "➡️" if s == self.selected_stat else "\u2000"
            lines.append(f"{pointer} {STAT_EMOJI.get(s, '')} **{STAT_NAMES[s]} ({s})** — {self.values[s]}")
        embed.add_field(name="Stats", value="\n".join(lines), inline=False)
        embed.add_field(name="Points Remaining", value=f"**{self.points_remaining}** / {POINT_BUY_POOL}",
                         inline=True)
        race_str = format_race_display(self.race)
        if self.race_description:
            race_str += f"\n*{self.race_description}*"
        embed.add_field(name="Identity", value=f"Race: {race_str}\nGender: {self.gender}", inline=True)
        embed.add_field(name=f"Selected — {STAT_NAMES[self.selected_stat]}",
                         value=STAT_EFFECTS[self.selected_stat], inline=False)
        embed.set_footer(text=f"Every stat starts at {BASE_STAT_VALUE} · {MAX_STAT_VALUE} max per stat · "
                               f"Class and equipment will be chosen on adventure start.")
        return embed

    async def _guard(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your character creation.", ephemeral=True)
            return False
        return True

    async def _on_select(self, interaction: discord.Interaction):
        if not await self._guard(interaction):
            return
        self.selected_stat = interaction.data["values"][0]
        self._rebuild()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def _on_plus(self, interaction: discord.Interaction):
        if not await self._guard(interaction):
            return
        if self.points_remaining > 0 and self.values[self.selected_stat] < MAX_STAT_VALUE:
            self.values[self.selected_stat] += 1
        self._rebuild()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def _on_minus(self, interaction: discord.Interaction):
        if not await self._guard(interaction):
            return
        if self.values[self.selected_stat] > BASE_STAT_VALUE:
            self.values[self.selected_stat] -= 1
        self._rebuild()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def _on_reset(self, interaction: discord.Interaction):
        if not await self._guard(interaction):
            return
        self.values = {s: BASE_STAT_VALUE for s in STATS}
        self._rebuild()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def _on_confirm(self, interaction: discord.Interaction):
        if not await self._guard(interaction):
            return
        if len(await adb(db.get_user_characters, self.user_id)) >= 6:
            await interaction.response.edit_message(
                content="You already have 6 characters (the maximum limit) -- creation cancelled.", embed=None, view=None)
            self.stop()
            return

        from mechanics.social.races import format_race_display
        leftover = self.points_remaining
        char = await adb(db.create_character,
            self.user_id, self.name, char_class="Adventurer", class_description="",
            stats=self.values, gold=STARTING_GOLD, pending_stat_points=leftover,
            gender=self.gender, scenario=self.scenario,
            race=self.race, race_description=self.race_description
        )
        equipment = await adb(db.get_equipment, self.user_id)

        embed = build_character_sheet_embed(char, equipment, title_prefix="✨ Character Created: ")
        embed.set_footer(text="Use /adventure start to embark on a quest and pick your scenario loadout.")

        await interaction.response.edit_message(content=None, embed=embed, view=None)
        self.stop()

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True


class CustomRaceModal(discord.ui.Modal, title="Describe Your Custom Race"):
    race_name = discord.ui.TextInput(
        label="Race / Species Name", placeholder="e.g. Kitsune-Vampire, Star-Elf...", max_length=50)
    race_desc = discord.ui.TextInput(
        label="Race Description (optional)", style=discord.TextStyle.paragraph,
        placeholder="Physical traits, species quirks, fur/tail features, or sensory traits",
        max_length=300, required=False)

    def __init__(self, name: str, gender: str, scenario: str = "fantasy"):
        super().__init__()
        self.name = name
        self.gender = gender
        self.scenario = scenario

    async def on_submit(self, interaction: discord.Interaction):
        race = str(self.race_name)
        desc = str(self.race_desc)
        view = StatAllocationView(interaction.user.id, self.name, self.gender, race=race, race_description=desc, scenario=self.scenario)
        await interaction.response.send_message(
            content=f"Race: **{race}** -- {desc}\n\nNow allocate your stats:", embed=view.build_embed(), view=view, ephemeral=True)


class RaceSelectView(discord.ui.View):
    def __init__(self, name: str, gender: str, scenario: str = "fantasy"):
        super().__init__(timeout=180)
        self.name = name
        self.gender = gender
        self.scenario = scenario

        races = [
            "Human", "Elf", "Dwarf", "Dark Elf", "Orc", "Goblin", "Gnome", "Halfling",
            "Beastfolk / Anthro", "Half-Beast / Hybrid", "Cyborg", "Android / Synth", "Mutant", "Alien",
            "Dragonkin", "Angel", "Demon", "Tiefling"
        ]
        options = [discord.SelectOption(label=r) for r in races]
        options.append(discord.SelectOption(
            label="Custom Race...", value="__custom__", description="Type your own race/species & traits"))

        select = discord.ui.Select(placeholder="Choose your race/species...", options=options)
        select.callback = self._on_select
        self.add_item(select)

    async def _on_select(self, interaction: discord.Interaction):
        value = interaction.data["values"][0]
        if value == "__custom__":
            await interaction.response.send_modal(CustomRaceModal(self.name, self.gender, scenario=self.scenario))
        else:
            view = StatAllocationView(interaction.user.id, self.name, self.gender, race=value, race_description="", scenario=self.scenario)
            await interaction.response.edit_message(
                content=f"Race: **{value}**.\n\nNow allocate your stats:", embed=view.build_embed(), view=view)


class CustomGenderModal(discord.ui.Modal, title="Describe Your Gender"):
    gender_text = discord.ui.TextInput(
        label="Gender", placeholder="e.g. Non-binary, Agender, Genderfluid...", max_length=50)

    def __init__(self, name: str, scenario: str = "fantasy"):
        super().__init__()
        self.name = name
        self.scenario = scenario

    async def on_submit(self, interaction: discord.Interaction):
        gender = str(self.gender_text)
        view = RaceSelectView(self.name, gender, scenario=self.scenario)
        await interaction.response.send_message(
            content=f"Gender: **{gender}**. Now select your race/species:", view=view, ephemeral=True)


class GenderSelectView(discord.ui.View):
    def __init__(self, name: str, scenario: str = "fantasy"):
        super().__init__(timeout=180)
        self.name = name
        self.scenario = scenario

        options = [discord.SelectOption(label=g) for g in GENDER_OPTIONS]
        options.append(discord.SelectOption(
            label="Custom...", value="__custom__", description="Type your own gender identity"))
        select = discord.ui.Select(placeholder="Choose your gender...", options=options)
        select.callback = self._on_select
        self.add_item(select)

    async def _on_select(self, interaction: discord.Interaction):
        value = interaction.data["values"][0]
        if value == "__custom__":
            await interaction.response.send_modal(CustomGenderModal(self.name, scenario=self.scenario))
        else:
            view = RaceSelectView(self.name, value, scenario=self.scenario)
            await interaction.response.edit_message(
                content=f"Gender: **{value}**. Now select your race/species:", view=view)


class ScenarioSelectView(discord.ui.View):
    """Step 1 of character creation: Pick a scenario to tie to the hero."""

    def __init__(self, name: str):
        super().__init__(timeout=180)
        self.name = name

        scenarios = load_scenarios()
        options = [
            discord.SelectOption(label=entry["name"], value=key, description=entry["description"][:100])
            for key, entry in scenarios.items()
        ]
        select = discord.ui.Select(placeholder="Choose a scenario...", options=options)
        select.callback = self._on_select
        self.add_item(select)

    async def _on_select(self, interaction: discord.Interaction):
        scenario_key = interaction.data["values"][0]
        scen_name = load_scenarios().get(scenario_key, {}).get("name", scenario_key)
        view = GenderSelectView(self.name, scenario=scenario_key)
        await interaction.response.edit_message(
            content=f"Scenario: **{scen_name}**. Next, select a gender:", view=view)


class ConfirmDeleteView(discord.ui.View):
    def __init__(self, user_id: int, char_name: str):
        super().__init__(timeout=30)
        self.user_id = user_id
        self.char_name = char_name

    @discord.ui.button(label="Confirm Delete", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your confirmation.", ephemeral=True)
            return
        await adb(db.delete_character, self.user_id)
        for child in self.children:
            child.disabled = True

        remaining = await adb(db.get_character, self.user_id)
        if remaining:
            msg = f"**{self.char_name}** has been retired. Switched active character to **{remaining['name']}**."
        else:
            msg = f"**{self.char_name}** has been retired. Farewell, adventurer. You can now `/character create` a new hero."

        await interaction.response.edit_message(content=msg, embed=None, view=self)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your confirmation.", ephemeral=True)
            return
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="Deletion cancelled.", embed=None, view=self)
        self.stop()

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True


class CharacterCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    character_group = app_commands.Group(name="character", description="Manage your Hikayat character")

    @character_group.command(name="create", description="Create a new character (up to 6 maximum)")
    @app_commands.describe(name="Your character's name")
    async def create(self, interaction: discord.Interaction, name: str):
        existing = await adb(db.get_user_characters, interaction.user.id)
        if len(existing) >= 6:
            names = ", ".join(f"**{c['name']}**" for c in existing)
            await interaction.response.send_message(
                f"You already have 6 characters (the maximum limit): {names}. "
                f"Use `/character switch` to change active character or `/character delete` to remove one.",
                ephemeral=True)
            return
        await interaction.response.send_message(
            f"Naming your hero **{name}**. Select a gender:",
            view=GenderSelectView(name), ephemeral=True)

    @character_group.command(name="list", description="List all your characters (up to 6)")
    async def list_characters(self, interaction: discord.Interaction):
        chars = await adb(db.get_user_characters, interaction.user.id)
        if not chars:
            await interaction.response.send_message(
                "You don't have any characters yet. Use `/character create` to make one.", ephemeral=True
            )
            return

        embed = discord.Embed(
            title=f"{interaction.user.display_name}'s Characters ({len(chars)}/6)",
            color=discord.Color.gold()
        )
        for char in chars:
            status_tag = "✅ **ACTIVE**" if char.get("is_active") else "💤 Inactive"
            session_note = ""
            if char.get("active_session_id"):
                session = await adb(db.get_session, char["active_session_id"])
                if session and session.get("status") == "active":
                    session_note = f"\n📖 Active Adventure: Scenario *{session.get('scenario', 'fantasy').title()}* (ID #{session['id']})"

            value = (
                f"**Class:** {char['char_class']}\n"
                f"**Level:** {char['level']} ({char['xp']} XP) | **Gold:** {char['gold']}\n"
                f"**Vitals:** ❤️ {char['hp']}/{char['max_hp']} | 💙 {char['mp']}/{char['max_mp']}"
                f"{session_note}"
            )
            embed.add_field(name=f"{status_tag} | {char['name']}", value=value, inline=False)

        embed.set_footer(text="Use /character switch [name] to change active character.")
        await interaction.response.send_message(embed=embed)

    @character_group.command(name="switch", description="Switch your active character")
    @app_commands.describe(name="Name of the character to activate")
    async def switch(self, interaction: discord.Interaction, name: str):
        switched = await adb(db.switch_character, interaction.user.id, name)
        if not switched:
            chars = await adb(db.get_user_characters, interaction.user.id)
            if not chars:
                await interaction.response.send_message(
                    "You don't have any characters yet. Use `/character create` first.", ephemeral=True
                )
            else:
                names = ", ".join(f"**{c['name']}**" for c in chars)
                await interaction.response.send_message(
                    f"No character found named '{name}'. Your characters: {names}.", ephemeral=True
                )
            return

        equipment = await adb(db.get_equipment, interaction.user.id)
        equipped_count = sum(1 for item in equipment.values() if item)

        session_note = "No active adventure. Use `/adventure start` or `/adventure custom`."
        if switched.get("active_session_id"):
            session = await adb(db.get_session, switched["active_session_id"])
            if session and session.get("status") == "active":
                session_note = f"In active adventure: *{session.get('scene_title', 'In progress')}*! Use `/resume` to continue."

        embed = discord.Embed(
            title=f"🔄 Switched Active Character to {switched['name']}",
            description=f"**Class:** {switched['char_class']} (Level {switched['level']})\n"
                        f"**Vitals:** ❤️ {switched['hp']}/{switched['max_hp']} | 💙 {switched['mp']}/{switched['max_mp']} | Gold {switched['gold']}\n"
                        f"**Equipped:** {equipped_count} item(s)\n"
                        f"**Adventure:** {session_note}",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed)

    @switch.autocomplete("name")
    async def switch_autocomplete(self, interaction: discord.Interaction, current: str):
        chars = await adb(db.get_user_characters, interaction.user.id)
        current_lower = current.lower()
        choices = []
        for c in chars:
            if current_lower and current_lower not in c["name"].lower():
                continue
            active_str = " (ACTIVE)" if c.get("is_active") else ""
            label = f"{c['name']} - Lvl {c['level']} {c['char_class']}{active_str}"
            choices.append(app_commands.Choice(name=label[:100], value=c["name"]))
        return choices

    @character_group.command(name="sheet", description="View your character sheet")
    async def sheet(self, interaction: discord.Interaction):
        char = await adb(db.get_character, interaction.user.id)
        if not char:
            await interaction.response.send_message(
                "You don't have a character yet. Use `/character create` first.", ephemeral=True)
            return
        equipment = await adb(db.get_equipment, interaction.user.id)
        embed = build_character_sheet_embed(char, equipment)
        await interaction.response.send_message(embed=embed)

    @character_group.command(name="delete", description="Delete your character (irreversible)")
    async def delete(self, interaction: discord.Interaction):
        char = await adb(db.get_character, interaction.user.id)
        if not char:
            await interaction.response.send_message("You don't have a character.", ephemeral=True)
            return
        await interaction.response.send_message(
            f"Are you sure you want to permanently delete **{char['name']}**? This cannot be undone.",
            view=ConfirmDeleteView(interaction.user.id, char["name"]), ephemeral=True)

    @app_commands.command(name="allocate",
                           description="Spend unspent stat points from leveling up or quests")
    async def allocate(self, interaction: discord.Interaction):
        """Standalone anytime stat allocation command -- distinct from
        /character levelup only in name/discoverability; both spend from the
        same `pending_stat_points` pool (fed by leveling up and by any
        point-buy points saved unspent at creation), via the same
        interactive button UI (StatPointView, defined in cogs/adventure.py
        since it's also auto-posted right after a level-up)."""
        char = await adb(db.get_character, interaction.user.id)
        if not char:
            await interaction.response.send_message(
                "You don't have a character yet. Use `/character create` first.", ephemeral=True)
            return
        if char["pending_stat_points"] <= 0:
            await interaction.response.send_message(
                "You have no unspent stat points saved up right now. You earn more by leveling up "
                "during `/adventure`, or by saving some at `/character create`.", ephemeral=True)
            return
        from cogs.adventure import StatPointView  # local import avoids a circular import at module load
        view = StatPointView(interaction.user.id)
        await interaction.response.send_message(
            f"You have **{char['pending_stat_points']}** stat point(s) saved up. Choose where to spend them:",
            view=view, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(CharacterCog(bot))
