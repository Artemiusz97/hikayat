import discord
from discord import app_commands
from discord.ext import commands

import db


def build_debug_embed(user_id: int) -> discord.Embed:
    s = db.get_settings(user_id)
    stat_mode = s.get("debug_stat_mode", "off")
    check_mode = s.get("debug_check_mode", "off")
    reveal_mode = s.get("debug_reveal_all_info", 0)

    embed = discord.Embed(
        title="🛠️ Hikayat Debug Menu",
        description=(
            "Toggle debug overrides for your character's stats, skill checks, and NPC profiles. "
            "By default, all options are disabled. When disabled, your stats, "
            "success rates, and disclosure levels return to normal."
        ),
        color=discord.Color.dark_orange()
    )

    opt1 = "🟩 **ENABLED** (Stats set to 10)" if stat_mode == "max" else "⬜ Disabled"
    opt2 = "🟩 **ENABLED** (Stats set to 1)" if stat_mode == "min" else "⬜ Disabled"

    opt3 = "🟩 **ENABLED**" if check_mode == "always_success" else "⬜ Disabled"
    opt4 = "🟩 **ENABLED**" if check_mode == "always_fail" else "⬜ Disabled"
    opt5 = "🟩 **ENABLED**" if check_mode == "always_crit_success" else "⬜ Disabled"
    opt6 = "🟩 **ENABLED**" if check_mode == "always_crit_fail" else "⬜ Disabled"
    opt7 = "🟩 **ENABLED** (All traits, mannerisms, intimate profiles & past history revealed)" if reveal_mode else "⬜ Disabled"

    embed.add_field(name="1. Maximize All Stats", value=opt1, inline=False)
    embed.add_field(name="2. Minimize All Stats", value=opt2, inline=False)
    embed.add_field(name="3. Always Successful (No Crit)", value=opt3, inline=False)
    embed.add_field(name="4. Always Fail (No Crit)", value=opt4, inline=False)
    embed.add_field(name="5. Always Critical Success", value=opt5, inline=False)
    embed.add_field(name="6. Always Critical Failure", value=opt6, inline=False)
    embed.add_field(name="7. Reveal All NPC Profiles & History", value=opt7, inline=False)

    char = db.get_character(user_id)
    if char:
        vitals = f"❤️ HP: **{char['hp']}/{char['max_hp']}** | 🔷 MP: **{char['mp']}/{char['max_mp']}**"
    else:
        vitals = "*(No active character)*"
    embed.add_field(name="❤️ Character Vitals (Instant Actions: 🩸 Set 1 HP | 💖 Full Heal)", value=vitals, inline=False)

    active_summary = []
    if stat_mode != "off":
        active_summary.append(f"Stat Override: `{stat_mode.upper()}`")
    if check_mode != "off":
        active_summary.append(f"Check Override: `{check_mode.upper()}`")
    if reveal_mode:
        active_summary.append("NPC Reveal: `ENABLED`")

    footer_text = "Active Overrides: " + (", ".join(active_summary) if active_summary else "None")
    embed.set_footer(text=footer_text)
    return embed


class DebugMenuView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=300)
        self.user_id = user_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "❌ Only the player who opened this debug menu can interact with it.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="1. Max Stats", style=discord.ButtonStyle.primary, row=0)
    async def toggle_max_stats(self, interaction: discord.Interaction, button: discord.ui.Button):
        s = db.get_settings(self.user_id)
        new_mode = "off" if s.get("debug_stat_mode") == "max" else "max"
        db.update_settings(self.user_id, debug_stat_mode=new_mode)
        embed = build_debug_embed(self.user_id)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="2. Min Stats", style=discord.ButtonStyle.secondary, row=0)
    async def toggle_min_stats(self, interaction: discord.Interaction, button: discord.ui.Button):
        s = db.get_settings(self.user_id)
        new_mode = "off" if s.get("debug_stat_mode") == "min" else "min"
        db.update_settings(self.user_id, debug_stat_mode=new_mode)
        embed = build_debug_embed(self.user_id)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="3. Always Success", style=discord.ButtonStyle.success, row=1)
    async def toggle_always_success(self, interaction: discord.Interaction, button: discord.ui.Button):
        s = db.get_settings(self.user_id)
        new_mode = "off" if s.get("debug_check_mode") == "always_success" else "always_success"
        db.update_settings(self.user_id, debug_check_mode=new_mode)
        embed = build_debug_embed(self.user_id)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="4. Always Fail", style=discord.ButtonStyle.danger, row=1)
    async def toggle_always_fail(self, interaction: discord.Interaction, button: discord.ui.Button):
        s = db.get_settings(self.user_id)
        new_mode = "off" if s.get("debug_check_mode") == "always_fail" else "always_fail"
        db.update_settings(self.user_id, debug_check_mode=new_mode)
        embed = build_debug_embed(self.user_id)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="5. Always Crit Success", style=discord.ButtonStyle.success, row=2)
    async def toggle_always_crit_success(self, interaction: discord.Interaction, button: discord.ui.Button):
        s = db.get_settings(self.user_id)
        new_mode = "off" if s.get("debug_check_mode") == "always_crit_success" else "always_crit_success"
        db.update_settings(self.user_id, debug_check_mode=new_mode)
        embed = build_debug_embed(self.user_id)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="6. Always Crit Fail", style=discord.ButtonStyle.danger, row=2)
    async def toggle_always_crit_fail(self, interaction: discord.Interaction, button: discord.ui.Button):
        s = db.get_settings(self.user_id)
        new_mode = "off" if s.get("debug_check_mode") == "always_crit_fail" else "always_crit_fail"
        db.update_settings(self.user_id, debug_check_mode=new_mode)
        embed = build_debug_embed(self.user_id)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Reduce HP to 1", style=discord.ButtonStyle.danger, emoji="🩸", row=3)
    async def set_hp_to_1(self, interaction: discord.Interaction, button: discord.ui.Button):
        char = db.get_character(self.user_id)
        if not char:
            await interaction.response.send_message("❌ No active character found.", ephemeral=True)
            return
        db.set_hp_to_one(self.user_id)
        embed = build_debug_embed(self.user_id)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Full Heal", style=discord.ButtonStyle.success, emoji="💖", row=3)
    async def full_heal_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        char = db.get_character(self.user_id)
        if not char:
            await interaction.response.send_message("❌ No active character found.", ephemeral=True)
            return
        db.heal_full(self.user_id)
        embed = build_debug_embed(self.user_id)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="7. Force Enemy", style=discord.ButtonStyle.danger, row=3)
    async def force_enemy(self, interaction: discord.Interaction, button: discord.ui.Button):
        session_id = db.get_active_session_id_for_user(self.user_id)
        if session_id:
            from mechanics.combat.enemies import generate_scenario_enemy
            dummy = generate_scenario_enemy("fantasy", "Debug", 1, custom_name="Debug Training Dummy", custom_archetype="Guardian")
            dummy["hp"] = 100
            dummy["max_hp"] = 100
            db.update_session_enemies(session_id, [dummy])
            await interaction.response.send_message("Enemy encounter triggered! Combat will begin on the next turn. It will automatically disable once the enemy is defeated.", ephemeral=True)
        else:
            await interaction.response.send_message("No active session to trigger an encounter in.", ephemeral=True)

    @discord.ui.button(label="8. Reveal All NPC Info", style=discord.ButtonStyle.primary, row=4)
    async def toggle_reveal_all(self, interaction: discord.Interaction, button: discord.ui.Button):
        s = db.get_settings(self.user_id)
        new_mode = 0 if s.get("debug_reveal_all_info") else 1
        db.update_settings(self.user_id, debug_reveal_all_info=new_mode)
        embed = build_debug_embed(self.user_id)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Reset All Overrides", style=discord.ButtonStyle.secondary, row=4)
    async def reset_all(self, interaction: discord.Interaction, button: discord.ui.Button):
        db.update_settings(self.user_id, debug_stat_mode="off", debug_check_mode="off", debug_reveal_all_info=0)
        embed = build_debug_embed(self.user_id)
        await interaction.response.edit_message(embed=embed, view=self)


class DebugCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="debug", description="Toggle debug options for stats, skill checks, and character profiles")
    @app_commands.choices(option=[
        app_commands.Choice(name="1. Maximize All Stats", value="max_stats"),
        app_commands.Choice(name="2. Minimize All Stats", value="min_stats"),
        app_commands.Choice(name="3. Always Successful (No Crit)", value="always_success"),
        app_commands.Choice(name="4. Always Fail (No Crit)", value="always_fail"),
        app_commands.Choice(name="5. Always Critical Success", value="always_crit_success"),
        app_commands.Choice(name="6. Always Critical Failure", value="always_crit_fail"),
        app_commands.Choice(name="7. Force Enemy Encounter", value="force_enemy"),
        app_commands.Choice(name="8. Reveal All NPC Profiles & History", value="reveal_all_info"),
        app_commands.Choice(name="Reduce HP to 1 (Instant)", value="hp_to_1"),
        app_commands.Choice(name="Full Heal (Instant)", value="full_heal"),
        app_commands.Choice(name="Reset All (Disable)", value="off"),
    ])
    async def debug_command(self, interaction: discord.Interaction, option: app_commands.Choice[str] | None = None):
        user_id = interaction.user.id
        if option is not None:
            val = option.value
            if val == "max_stats":
                s = db.get_settings(user_id)
                new_stat = "off" if s.get("debug_stat_mode") == "max" else "max"
                db.update_settings(user_id, debug_stat_mode=new_stat)
            elif val == "min_stats":
                s = db.get_settings(user_id)
                new_stat = "off" if s.get("debug_stat_mode") == "min" else "min"
                db.update_settings(user_id, debug_stat_mode=new_stat)
            elif val in ("always_success", "always_fail", "always_crit_success", "always_crit_fail"):
                s = db.get_settings(user_id)
                new_check = "off" if s.get("debug_check_mode") == val else val
                db.update_settings(user_id, debug_check_mode=new_check)
            elif val == "force_enemy":
                session_id = db.get_active_session_id_for_user(user_id)
                if session_id:
                    from mechanics.combat.enemies import generate_scenario_enemy
                    dummy = generate_scenario_enemy("fantasy", "Debug", 1, custom_name="Debug Training Dummy", custom_archetype="Guardian")
                    dummy["hp"] = 100
                    dummy["max_hp"] = 100
                    db.update_session_enemies(session_id, [dummy])
                    await interaction.response.send_message("Enemy encounter triggered! Combat will begin on the next turn.", ephemeral=True)
                    return
                else:
                    await interaction.response.send_message("No active session to trigger an encounter in.", ephemeral=True)
                    return
            elif val == "reveal_all_info":
                s = db.get_settings(user_id)
                new_rev = 0 if s.get("debug_reveal_all_info") else 1
                db.update_settings(user_id, debug_reveal_all_info=new_rev)
            elif val == "hp_to_1":
                char = db.get_character(user_id)
                if char:
                    db.set_hp_to_one(user_id)
            elif val == "full_heal":
                char = db.get_character(user_id)
                if char:
                    db.heal_full(user_id)
            elif val == "off":
                db.update_settings(user_id, debug_stat_mode="off", debug_check_mode="off", debug_reveal_all_info=0)

        embed = build_debug_embed(user_id)
        view = DebugMenuView(user_id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(DebugCog(bot))
