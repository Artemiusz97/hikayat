import discord
from discord import app_commands
from discord.ext import commands

import db
from db import adb
from config import (
    APP_VERSION,
    IMAGE_ROUTER_API_KEY, IMAGE_ROUTER_MODEL,
    LLM_MODEL, LLM_BASE_URL,
    NSFW_LLM_MODEL, NSFW_LLM_BASE_URL,
)
from llm_client import call_llm_text, get_candidate_models
import scenario_data
from scenario_data import is_nsfw_scenario


class SettingsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    settings_group = app_commands.Group(name="settings", description="Your personal Hikayat preferences")

    async def _handle_model_info(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        # Determine active session and whether NSFW routing is active for this user
        session_id = await adb(db.get_active_session_id_for_user, interaction.user.id)
        session = (await adb(db.get_session, session_id)) if session_id else None
        is_nsfw = False
        scen_name = "None"
        if session:
            scen_key = session.get("scenario")
            is_nsfw = is_nsfw_scenario(scen_key)
            try:
                scen_dict = scenario_data.get_scenario(scen_key)
                scen_name = scen_dict.get("name", scen_key)
            except Exception:
                scen_name = str(scen_key)

        has_nsfw_config = bool(NSFW_LLM_MODEL and NSFW_LLM_BASE_URL)
        active_is_nsfw = is_nsfw and has_nsfw_config
        active_model = NSFW_LLM_MODEL if active_is_nsfw else LLM_MODEL
        active_url = NSFW_LLM_BASE_URL if active_is_nsfw else LLM_BASE_URL

        # Get the full active candidate model chain
        candidate_pairs = get_candidate_models(is_nsfw=active_is_nsfw)
        cascade_chain_str = " ➔ ".join(f"`{m}`" for _, m in candidate_pairs)

        from llm_client import probe_model_capabilities, get_llm_telemetry
        
        # Probe primary candidate capabilities
        primary_client = candidate_pairs[0][0] if candidate_pairs else None
        cap = await probe_model_capabilities(primary_client, active_model) if primary_client else {"json_mode": True, "status": "ok"}
        has_warning = not cap.get("json_mode")

        system_prompt = (
            "You are an AI assistant. State clearly what model architecture or family you are, "
            "who created you, and any details you know about your version or identity. "
            "Be concise (2-3 sentences)."
        )
        user_prompt = "What LLM model are you currently running on?"
        try:
            reply = await call_llm_text(system_prompt, user_prompt, is_nsfw=active_is_nsfw)
            embed_color = discord.Color.gold() if has_warning else (discord.Color.magenta() if active_is_nsfw else discord.Color.blue())
            embed = discord.Embed(
                title="🤖 LLM Model & Configuration Status",
                color=embed_color
            )
            embed.add_field(name="💬 LLM Self-Identification", value=reply, inline=False)
            
            if session:
                nsfw_badge = "🔥 NSFW Model Active" if active_is_nsfw else ("⚠️ Standard Model (No NSFW config)" if is_nsfw else "⚙️ Standard Model")
                embed.add_field(name="📖 Active Scenario", value=f"`{scen_name}` ({nsfw_badge})", inline=False)

            json_status_badge = "✅ Native JSON Mode Supported" if cap.get("json_mode") else "⚠️ Native JSON Mode Unsupported"
            embed.add_field(name="⚙️ Primary Model", value=f"`{active_model}`\n└─ {json_status_badge}", inline=True)
            embed.add_field(name="🌐 Endpoint Base URL", value=f"`{active_url}`", inline=True)
            embed.add_field(name="🔄 Active Fallback Cascade Chain", value=cascade_chain_str, inline=False)

            # Live Phase 12 Telemetry & Circuit-Breaker Status
            telemetry = get_llm_telemetry()
            t_calls = telemetry.get("total_calls", 0)
            t_ok = telemetry.get("successful_calls", 0)
            t_fail = telemetry.get("failed_calls", 0)
            t_fb = telemetry.get("fallback_activations", 0)
            cbs = telemetry.get("circuit_breakers", {}) or {}
            cb_lines = []
            for m_slug, cb_info in list(cbs.items())[:5]:
                is_open = cb_info.get("is_open", False)
                rem_s = cb_info.get("cooldown_remaining_s", 0)
                badge = f"🔴 OPEN ({rem_s}s)" if is_open else "🟢 CLOSED"
                cb_lines.append(f"• `{m_slug}`: {badge}")
            cb_summary = "\n".join(cb_lines) if cb_lines else "• All endpoints healthy (🟢 CLOSED)"
            embed.add_field(
                name="📊 Live LLM Telemetry & Circuit Breakers",
                value=(
                    f"**Calls:** `{t_calls}` (`{t_ok}` ok / `{t_fail}` failed) • **Failovers:** `{t_fb}`\n"
                    f"{cb_summary}"
                ),
                inline=False
            )

            if has_warning:
                embed.add_field(
                    name="⚠️ Compatibility Notice",
                    value=(
                        f"Model `{active_model}` rejects OpenAI-standard `response_format` JSON enforcement.\n"
                        f"Hikayat will use plaintext markdown JSON fallback. If the model truncates, "
                        f"it will automatically failover to `{candidate_pairs[1][1] if len(candidate_pairs) > 1 else 'fallback'}`."
                    ),
                    inline=False
                )

            if has_nsfw_config and not active_is_nsfw:
                from llm_client import _nsfw_client, probe_model_capabilities
                nsfw_cap = await probe_model_capabilities(_nsfw_client, NSFW_LLM_MODEL) if _nsfw_client else None
                nsfw_status = " (✅ Native JSON Mode)" if (nsfw_cap and nsfw_cap.get("json_mode")) else (" (⚠️ Markdown JSON fallback)" if (nsfw_cap and nsfw_cap.get("status") == "ok") else "")
                embed.add_field(name="🔥 Configured NSFW Model", value=f"`{NSFW_LLM_MODEL}`{nsfw_status}", inline=False)


            embed.set_footer(text=f"Hikayat v{APP_VERSION}")
            await interaction.followup.send(embed=embed)
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to reach LLM (`{active_model}`): `{e}`", ephemeral=True)

    @app_commands.command(name="model", description="Prompt the LLM to identify the model it is currently running on")
    async def model_command(self, interaction: discord.Interaction):
        await self._handle_model_info(interaction)

    @settings_group.command(name="model_info", description="Prompt the LLM to identify the model it is currently running on")
    async def model_info(self, interaction: discord.Interaction):
        await self._handle_model_info(interaction)


    @settings_group.command(name="verbosity", description="How the narrator should write scenes")
    @app_commands.choices(style=[
        app_commands.Choice(name="Shakespearean (poetic, theatrical Elizabethan prose)", value="shakespearean"),
        app_commands.Choice(name="Vivid (vivid, atmospheric RPG prose)", value="vivid"),
        app_commands.Choice(name="Normal (clear, contemporary descriptive style)", value="normal"),
        app_commands.Choice(name="Direct (momentum-driven story & dialogue without filler)", value="direct"),
        app_commands.Choice(name="Concise (brief, direct action & key updates)", value="concise"),
    ])
    async def verbosity(self, interaction: discord.Interaction, style: app_commands.Choice[str]):
        await adb(db.update_settings, interaction.user.id, verbosity=style.value)
        msg = f"Narration style set to **{style.name}**. This applies immediately."
        await interaction.response.send_message(msg, ephemeral=True)

    @settings_group.command(name="dialogue", description="Toggle spoken NPC dialogue in narration")
    @app_commands.choices(state=[
        app_commands.Choice(name="Off (no character quotes, pure narration)", value="off"),
        app_commands.Choice(name="Minimal (mostly narration, 1-2 short quotes)", value="minimal"),
        app_commands.Choice(name="Balanced (50/50 mix of two-way dialogue & narration)", value="balanced"),
        app_commands.Choice(name="Adaptive (dynamic: tactical barks in combat, rich dialogue in social)", value="adaptive"),
        app_commands.Choice(name="Rich (dialogue primary, cinematic stage directions)", value="rich"),
    ])
    async def dialogue(self, interaction: discord.Interaction, state: app_commands.Choice[str]):
        await adb(db.update_settings, interaction.user.id, dialogue_mode=state.value)
        msg = f"Dialogue style set to **{state.name}**. This applies immediately."
        await interaction.response.send_message(msg, ephemeral=True)

    @settings_group.command(name="image_generation", description="Toggle AI scene images on/off by default")
    @app_commands.choices(state=[
        app_commands.Choice(name="On", value="on"),
        app_commands.Choice(name="Off", value="off"),
    ])
    async def image_generation(self, interaction: discord.Interaction, state: app_commands.Choice[str]):
        if state.value == "on" and not IMAGE_ROUTER_API_KEY:
            await interaction.response.send_message(
                "Image generation isn't configured on this bot yet (no IMAGE_ROUTER_API_KEY set "
                "in .env), so turning it on won't do anything until that's set up.", ephemeral=True)
            return
        await adb(db.update_settings, interaction.user.id, image_gen_enabled=1 if state.value == "on" else 0)
        await interaction.response.send_message(
            f"Scene image generation set to **{state.name}**. This applies immediately.", ephemeral=True)

    @settings_group.command(name="image_model", description="Override the ImageRouter model slug used for your scenes")
    async def image_model(self, interaction: discord.Interaction, model: str):
        await adb(db.update_settings, interaction.user.id, image_model=model)
        await interaction.response.send_message(
            f"Your image model override is now `{model}`. Leave this unset to use the bot "
            f"default (`{IMAGE_ROUTER_MODEL}`). Check https://imagerouter.io/models for valid slugs.",
            ephemeral=True)

    @settings_group.command(name="combat_ui_style",
                             description="Choose combat interface layout (JRPG Battle Deck buttons or Categorized Dropdowns)")
    @app_commands.choices(style=[
        app_commands.Choice(name="JRPG Battle Deck (Default — Category Buttons & Submenus)", value="battle_deck"),
        app_commands.Choice(name="Multi-Dropdown Dashboard (All Categorized Dropdowns on Screen)", value="multi_dropdown"),
    ])
    async def combat_ui_style(self, interaction: discord.Interaction, style: app_commands.Choice[str]):
        await adb(db.update_settings, interaction.user.id, combat_ui_style=style.value)
        await interaction.response.send_message(
            f"Combat UI style set to **{style.name}**. This applies immediately in your combat encounters.", ephemeral=True)

    @settings_group.command(name="result_display",
                             description="Toggle between detailed and compact result window after each action")
    @app_commands.choices(mode=[
        app_commands.Choice(name="Detailed (show vitals, relationships, factions & story clues)", value="detailed"),
        app_commands.Choice(name="Compact (show narrative, check result & loot only)", value="compact"),
    ])
    async def result_display(self, interaction: discord.Interaction, mode: app_commands.Choice[str]):
        await adb(db.update_settings, interaction.user.id, result_display=mode.value)
        await interaction.response.send_message(
            f"Result window set to **{mode.name}**. This applies immediately.", ephemeral=True)

    @settings_group.command(name="percentages",
                             description="Toggle displaying raw success percentages on action choices")
    @app_commands.choices(state=[
        app_commands.Choice(name="On (Show e.g. 50% or 100%)", value="on"),
        app_commands.Choice(name="Off (Hide numbers; show stat and action only)", value="off"),
    ])
    async def percentages(self, interaction: discord.Interaction, state: app_commands.Choice[str]):
        val = 1 if state.value == "on" else 0
        await adb(db.update_settings, interaction.user.id, show_percentages=val)
        await interaction.response.send_message(
            f"Raw percentages on action choices set to **{state.name}**. This applies immediately.", ephemeral=True)

    @settings_group.command(name="show", description="View your current settings")
    async def show(self, interaction: discord.Interaction):
        s = await adb(db.get_settings, interaction.user.id)
        embed = discord.Embed(title="Your Hikayat Settings", color=discord.Color.teal())
        embed.add_field(name="Verbosity", value=s["verbosity"].capitalize(), inline=True)
        dialogue_disp = s.get("dialogue_mode", "balanced").capitalize()
        embed.add_field(name="Dialogue", value=dialogue_disp, inline=True)
        embed.add_field(name="Image Generation", value="On" if s["image_gen_enabled"] else "Off", inline=True)
        combat_ui_map = {
            "battle_deck": "JRPG Battle Deck (Default)",
            "multi_dropdown": "Multi-Dropdown Dashboard"
        }
        embed.add_field(name="Combat UI", value=combat_ui_map.get(s.get("combat_ui_style", "battle_deck"), "JRPG Battle Deck"),
                         inline=True)
        embed.add_field(name="Result Display",
                         value=s.get("result_display", "detailed").capitalize(),
                         inline=True)
        embed.add_field(name="Raw Percentages",
                         value="On" if s.get("show_percentages", 1) else "Off",
                         inline=True)
        embed.add_field(name="Image Model Override", value=s["image_model"] or "(using bot default)", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _send_help_embed(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="⚔️ Hikayat — Command Overview",
            description="Here is the complete list of available slash commands for Hikayat:",
            color=discord.Color.gold()
        )

        embed.add_field(
            name="⚔️ Adventure & Exploration",
            value=(
                "`/adventure start` — Begin a new adventure (select preset scenario or custom tag mixing).\n"
                "`/adventure leave` — Abandon your current adventure session.\n"
                "`/resume` or `/adventure resume` — Resume your active adventure scene.\n"
                "`/quest` — Open your Quest Log (Active, Notes, Campaign Goals, History).\n"
                "`/map` or `/location` — View the World Map and explore discovered regions.\n"
                "`/hub` (or `/device`, `/phone`) — Access your communication device & network hub."
            ),
            inline=False
        )

        embed.add_field(
            name="👤 Character Management",
            value=(
                "`/character create` — Create a hero (Gender ➔ Race ➔ Class ➔ Weapon ➔ Stats).\n"
                "`/character list` — List all your saved characters (up to 6 maximum).\n"
                "`/character sheet` — View your character stats, race, HP/MP, level, and equipment.\n"
                "`/character switch` — Switch between your saved characters.\n"
                "`/character delete` — Permanently retire a character.\n"
                "`/allocate` — Spend unspent stat points earned from leveling up, quests, or creation."
            ),
            inline=False
        )

        embed.add_field(
            name="🎒 Inventory & Gear",
            value=(
                "`/inventory show` — View inventory items, slot capacity, and equipped gear.\n"
                "`/inventory equip` — Equip a weapon, armor, shield, or accessory.\n"
                "`/inventory unequip` — Unequip an item from a slot.\n"
                "`/inventory drop` — Discard an item from your inventory."
            ),
            inline=False
        )

        embed.add_field(
            name="📇 Contacts & Factions",
            value=(
                "`/contacts` — View NPC contact list, relationship scores, and tier meters.\n"
                "`/factions` — View regional faction reputation standings and active perks."
            ),
            inline=False
        )

        embed.add_field(
            name="⚙️ Settings & System",
            value=(
                "`/help` or `/commands` — Display this complete command overview list.\n"
                "`/settings show` — View your current player preferences.\n"
                "`/settings verbosity` — Set narrator description detail level.\n"
                "`/settings dialogue` — Toggle spoken NPC quotes in narration.\n"
                "`/settings image_generation` — Toggle AI scene images on/off.\n"
                "`/settings result_display` — Toggle Detailed vs Compact turn outcomes.\n"
                "`/settings percentages` — Toggle displaying raw success percentages on choices.\n"
                "`/model` — Check active LLM model architecture & endpoint.\n"
                "`/debug` — Developer tools for state inspection & stat testing."
            ),
            inline=False
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="help", description="List all available Hikayat commands and their functions")
    async def help_command(self, interaction: discord.Interaction):
        await self._send_help_embed(interaction)

    @app_commands.command(name="commands", description="List all available Hikayat commands and their functions")
    async def commands_command(self, interaction: discord.Interaction):
        await self._send_help_embed(interaction)


async def setup(bot: commands.Bot):
    await bot.add_cog(SettingsCog(bot))

