import asyncio
import logging
import traceback

import discord
from discord import app_commands
from discord.ext import commands

import db
from config import DISCORD_TOKEN, is_channel_allowed

logging.basicConfig(level=logging.INFO)

INTENTS = discord.Intents.default()
# Slash commands + buttons/modals don't need message_content or member intents.

bot = commands.Bot(command_prefix="!hikayat-unused-", intents=INTENTS)

COGS = ["cogs.character", "cogs.adventure", "cogs.inventory", "cogs.settings", "cogs.contacts", "cogs.factions", "cogs.debug"]


@bot.tree.interaction_check
async def global_interaction_check(interaction: discord.Interaction) -> bool:
    parent_id = getattr(interaction.channel, "parent_id", None)
    if not is_channel_allowed(interaction.channel_id, parent_id):
        if not interaction.response.is_done():
            await interaction.response.send_message(
                "❌ This bot is not allowed to run commands in this channel.",
                ephemeral=True,
            )
        return False
    return True


@bot.check
async def global_command_check(ctx: commands.Context) -> bool:
    parent_id = getattr(ctx.channel, "parent_id", None)
    if not is_channel_allowed(ctx.channel.id, parent_id):
        await ctx.send("❌ This bot is not allowed to run commands in this channel.", delete_after=10)
        return False
    return True


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (id={bot.user.id})")
    async def _startup_tasks():
        if not getattr(bot, "_commands_synced", False):
            bot._commands_synced = True
            try:
                synced = await bot.tree.sync()
                print(f"Synced {len(synced)} slash commands.")
            except Exception as e:
                print(f"Warning: tree sync error (non-fatal): {e}")

        try:
            from llm_client import get_probe_candidate_groups, probe_model_capabilities
            groups = get_probe_candidate_groups()
            print("\n" + "-" * 55)
            print("🔍 [LLM Compatibility Probe]")

            # Standard models
            print("Standard Models:")
            std_candidates = groups.get("standard", [])
            if not std_candidates:
                print("  • (No standard models configured)")
            else:
                for item in std_candidates:
                    client = item["client"]
                    model_name = item["model"]
                    role = item["role"]
                    role_tag = f" ({role})" if role != "Primary" else ""
                    cap = await probe_model_capabilities(client, model_name)
                    if cap.get("json_mode"):
                        print(f"  • Model '{model_name}'{role_tag}: ✅ Native JSON Mode supported.")
                    elif cap.get("status") == "ok":
                        print(f"  • Model '{model_name}'{role_tag}: ⚠️ Native JSON Mode (response_format) UNSUPPORTED.")
                        print(f"    └─ Hikayat will use plaintext markdown JSON fallback.")
                    else:
                        print(f"  • Model '{model_name}'{role_tag}: ❌ Error contacting model: {cap.get('error')}")

            # NSFW models
            nsfw_candidates = groups.get("nsfw", [])
            print("\nNSFW Models:")
            if not nsfw_candidates:
                print("  • (Not configured — inherits standard model chain)")
            else:
                for item in nsfw_candidates:
                    client = item["client"]
                    model_name = item["model"]
                    role = item["role"]
                    role_tag = f" ({role})" if role != "Primary" else ""
                    cap = await probe_model_capabilities(client, model_name)
                    if cap.get("json_mode"):
                        print(f"  • Model '{model_name}'{role_tag}: ✅ Native JSON Mode supported.")
                    elif cap.get("status") == "ok":
                        print(f"  • Model '{model_name}'{role_tag}: ⚠️ Native JSON Mode (response_format) UNSUPPORTED.")
                        print(f"    └─ Hikayat will use plaintext markdown JSON fallback.")
                    else:
                        print(f"  • Model '{model_name}'{role_tag}: ❌ Error contacting model: {cap.get('error')}")

            print("-" * 55 + "\n")
        except Exception as e:
            print(f"Warning: LLM capability probe failed (non-fatal): {e}")

    asyncio.create_task(_startup_tasks())



@bot.event
async def on_interaction(interaction: discord.Interaction):
    """Gracefully handles button or select interactions from expired views or past bot restarts.
    Prevents 'Hikayat didn't respond in time' and seamlessly recovers the player's active scene."""
    if interaction.type != discord.InteractionType.component:
        return

    # Check if this component has an active View registered in memory
    try:
        view_store = getattr(interaction._state, "_view_store", None)
        if view_store:
            data = interaction.data or {}
            key = (data.get("component_type"), data.get("custom_id"))
            msg_id = interaction.message.id if interaction.message else None
            # If registered in memory, an active View callback is already running
            if (msg_id and key in view_store._views.get(msg_id, {})) or key in view_store._views.get(None, {}):
                return
            # Also check if custom_id exists across any registered views
            custom_id = data.get("custom_id")
            if custom_id:
                for v_dict in view_store._views.values():
                    if any(k[1] == custom_id for k in v_dict.keys()):
                        return
    except Exception:
        pass

    # Give any concurrently dispatching view a tiny moment
    await asyncio.sleep(0.05)

    if interaction.response.is_done():
        return

    # View listener was lost due to bot restart or long idle. Recover gracefully:
    try:
        session_id = db.get_active_session_id_for_user(interaction.user.id)
        if not session_id:
            await interaction.response.send_message(
                "⚠️ This message's buttons expired after an idle period or restart.\n"
                "Use `/resume` or `/adventure start` to start or continue your adventure!",
                ephemeral=True
            )
            return

        session = db.get_session(session_id)
        if not session or session.get("status") != "active":
            await interaction.response.send_message(
                "⚠️ This message's buttons expired after an idle period or restart.\n"
                "Use `/resume` to check your adventure!",
                ephemeral=True
            )
            return

        # Check if the interaction was on an ephemeral message
        is_ephemeral = bool(interaction.message and getattr(interaction.message.flags, "ephemeral", False))
        if is_ephemeral:
            await interaction.response.send_message(
                "⚠️ This menu expired after a restart or long idle. Use `/hub`, `/quest`, or `/resume` to reopen it!",
                ephemeral=True
            )
            return

        adventure_cog = bot.get_cog("AdventureCog")
        if adventure_cog:
            await interaction.response.defer(ephemeral=False)
            await adventure_cog._resend_current_scene(interaction, session, use_followup=True)
        else:
            await interaction.response.send_message(
                "🔄 Adventure found! Use `/resume` to continue.",
                ephemeral=True
            )
    except (discord.InteractionResponded, discord.errors.InteractionResponded):
        return
    except discord.HTTPException as e:
        if e.code == 40060:
            # 40060: Interaction has already been acknowledged by an active view
            return
        logging.getLogger("hikayat.bot").error(f"Error handling expired component interaction: {e}", exc_info=True)
    except Exception as e:
        logging.getLogger("hikayat.bot").error(f"Error handling expired component interaction: {e}", exc_info=True)
        if not interaction.response.is_done():
            try:
                await interaction.response.send_message(
                    "⚠️ This message's buttons expired after an idle period. Use `/resume` to refresh your scene!",
                    ephemeral=True
                )
            except discord.HTTPException:
                pass



@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    """Without this handler, an exception raised before the interaction is
    acknowledged just shows the user 'The application did not respond' with
    no explanation, and the traceback only shows up in the console."""
    traceback.print_exception(type(error), error, error.__traceback__)
    message = "Something went wrong running that command. It's been logged."
    try:
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
    except discord.HTTPException:
        pass


_lock_file_handle = None


def acquire_single_instance_lock():
    """Ensures only one instance of Hikayat runs at a time.
    Prevents duplicate Discord gateway connections, which cause '10062 Unknown interaction'
    and '40060 Already acknowledged' errors."""
    global _lock_file_handle
    import os
    import sys

    base_dir = os.path.dirname(os.path.abspath(__file__))
    lock_path = os.path.join(base_dir, ".bot.lock")
    pid_path = os.path.join(base_dir, ".bot.pid")

    try:
        _lock_file_handle = open(lock_path, "a+")
        if os.name == "nt":
            import msvcrt
            _lock_file_handle.seek(0)
            msvcrt.locking(_lock_file_handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(_lock_file_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

        with open(pid_path, "w") as f:
            f.write(str(os.getpid()))
    except (OSError, IOError):
        old_pid = None
        if os.path.exists(pid_path):
            try:
                with open(pid_path, "r") as f:
                    old_pid = f.read().strip()
            except Exception:
                pass
        print("\n" + "=" * 70)
        print("[!] CRITICAL: Another instance of Hikayat bot is already running" + (f" (PID {old_pid})" if old_pid else "") + "!")
        print("Running multiple bot instances simultaneously causes Discord gateway conflicts")
        print("and interaction errors (e.g. 10062 Unknown interaction / 40060 Already acknowledged).")
        print("Please terminate any other running bot windows before starting a new one.")
        print("=" * 70 + "\n")
        sys.exit(1)


async def main():
    db.init_db()
    async with bot:
        for cog in COGS:
            await bot.load_extension(cog)
        await bot.start(DISCORD_TOKEN)


if __name__ == "__main__":
    acquire_single_instance_lock()
    asyncio.run(main())
