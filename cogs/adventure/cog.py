from .game_loop_mixin import GameLoopMixin
from .merchant_mixin import MerchantMixin
from .faction_mixin import FactionMixin
import asyncio
import json
import logging
import random
import re
import time
import discord
from mechanics.system.concurrency import distributed_session_lock, LockAcquisitionError
from discord import app_commands
from discord.ext import commands
logger = logging.getLogger("hikayat.adventure")
import db
from db import adb
import game_engine
from services.turn_service import TurnService
import image_client
from character_data import (
    XP_REWARDS, STATS, STAT_NAMES, STAT_EMOJI, MAX_LEVEL, MAX_STAT_VALUE,
    get_item_icon, format_item_with_icon, get_class_templates, get_starting_weapons,
    get_starter_gear_by_class, get_starting_items, inventory_capacity
)
from cogs.character import build_character_sheet_embed
from db import STAT_COLUMN
from scenario_data import DEFAULT_SCENARIO, ScenarioError, load_scenarios, resolve_scenario_key
from skill_check import resolve_check, success_chance, CheckResult
from mechanics.combat.merchant import (
    apply_merchant_encounter_result as _apply_merchant_encounter_result,
    handle_talk_to_merchant as _handle_talk_to_merchant,
    build_merchant_embed as _merchant_embed,
    discounted_price as _discounted_price,
    sell_bonus_price as _sell_bonus_price,
    MerchantView,
    MerchantVoteView,
    BuySelectView,
    SellSelectView,
    RumorView,
)
from mechanics.social.races import normalize_race
from mechanics.social.persona import normalize_appearance
from mechanics.world.locations import is_location_engine_enabled, get_discovered_location_tree, is_hub_location
from mechanics.narrative.bounty import QUEST_TYPE_ICONS, get_quest_type_icon as _quest_type_icon
from mechanics.combat.items import parse_item_effect, apply_item_to_target
import unicodedata

from .embeds import *
from .embeds import (
    _RESULT_COLORS, _RESULT_TITLES, _build_bounties_embed, _build_bounty_board_embed,
    _build_campaign_goals_embed, _build_caseboard_embed, _build_history_embed,
    _build_main_quest_embed, _build_quest_log_embed, _choice_button_label,
    _format_items_gained, _format_items_gained_multi, _format_tracker_entity,
    _get_choice_emoji, _get_choice_quest_icon, _get_choice_skill_emoji,
    _get_quest_scenario_labels, _is_dialogue_partner, _location_text, _norm_name,
    _parse_status_effects, _party_vitals_text, _safe_add_field, _safe_int,
    _scenario_command_choices, _strip_leading_emojis, _tracker_group_text,
    _tracker_header, _truncate_embed_text, _truncate_field_name, _truncate_field_value,
)

from .views import *

class AdventureCog(commands.Cog, GameLoopMixin, MerchantMixin, FactionMixin):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._last_picks: dict[int, tuple[int, dict]] = {}

    @app_commands.command(name="resume", description="Resume your active adventure session")
    async def resume(self, interaction: discord.Interaction):
        await self._do_resume(interaction)

    async def _do_resume(self, interaction: discord.Interaction):
        if not interaction.response.is_done():
            try:
                await interaction.response.defer()
            except (discord.HTTPException, discord.NotFound):
                pass

        char = await adb(db.get_character, interaction.user.id)
        if not char:
            msg = "You need a character first. Use `/character create`."
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
            return

        session_id = await adb(db.get_active_session_id_for_user, interaction.user.id)
        if not session_id:
            msg = "You don't have an active adventure to resume. Start one with `/adventure start` or `/adventure custom`."
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
            return

        session = await adb(db.get_session, session_id)
        if not session or session["status"] != "active":
            msg = "You don't have an active adventure to resume. Start one with `/adventure start` or `/adventure custom`."
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
            return

        await self._resend_current_scene(interaction, session, use_followup=True)

    @app_commands.command(name="quest", description="View your Quest Log")
    async def quest(self, interaction: discord.Interaction):
        char = await adb(db.get_character, interaction.user.id)
        if not char:
            msg = "You need a character first. Use `/character create`."
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
            return

        session_id = await adb(db.get_active_session_id_for_user, interaction.user.id)
        if not session_id:
            msg = "No active adventure. Start one with `/adventure start` or `/adventure custom`."
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
            return

        embed = _build_quest_log_embed(session_id, tab="Main Quest")
        view = QuestLogView(session_id, current_tab="Main Quest")
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, view=view)
        else:
            await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="caseboard", description="Open your Investigation Caseboard & Evidence Archive")
    async def caseboard_cmd(self, interaction: discord.Interaction):
        char = await adb(db.get_character, interaction.user.id)
        if not char:
            msg = "You need a character first. Use `/character create`."
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
            return

        session_id = await adb(db.get_active_session_id_for_user, interaction.user.id)
        if not session_id:
            msg = "No active adventure. Start one with `/adventure start` or `/adventure custom`."
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
            return

        embed = _build_quest_log_embed(session_id, tab="Caseboard")
        view = QuestLogView(session_id, current_tab="Caseboard")
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, view=view)
        else:
            await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="location", description="View the World Map and explore discovered regions")
    async def location_cmd(self, interaction: discord.Interaction):
        await self._do_map(interaction)

    @app_commands.command(name="map", description="View the World Map and explore discovered regions")
    async def map_cmd(self, interaction: discord.Interaction):
        await self._do_map(interaction)

    async def _do_map(self, interaction: discord.Interaction):
        if not interaction.response.is_done():
            try:
                await interaction.response.defer(ephemeral=True)
            except (discord.HTTPException, discord.NotFound):
                pass
        char = await adb(db.get_character, interaction.user.id)
        if not char:
            await interaction.followup.send(
                "You need a character first. Use `/character create`.", ephemeral=True
            )
            return

        session_id = await adb(db.get_active_session_id_for_user, interaction.user.id)
        if not session_id:
            await interaction.followup.send(
                "No active adventure. Start one with `/adventure start` or `/adventure custom`.", ephemeral=True
            )
            return

        session = await adb(db.get_session, session_id)
        if not session or session["status"] != "active":
            await interaction.followup.send(
                "No active adventure session found.", ephemeral=True
            )
            return

        scen_key = session.get("scenario", "fantasy")
        cur_loc = session.get("current_location", "")
        char_name = char.get("name", "")
        from mechanics.world.locations import get_zone_summary_tree
        zones = get_zone_summary_tree(session_id, scen_key, current_loc=cur_loc, char_name=char_name)
        embed = build_world_map_embed(session_id, scen_key, current_loc=cur_loc, char_name=char_name, zones=zones)
        view = ZoneSelectView(self, session_id, scen_key, current_loc=cur_loc, char_name=char_name, sync=session.get("mode") == "sync", zones_summary=zones)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="hub", description="Access your communication device and network hub (Smartphone, Cyberdeck, Comms Pad)")
    async def hub_cmd(self, interaction: discord.Interaction):
        await self._do_hub(interaction)

    @app_commands.command(name="device", description="Access your communication device and network hub (Smartphone, Cyberdeck, Comms Pad)")
    async def device_cmd(self, interaction: discord.Interaction):
        await self._do_hub(interaction)

    @app_commands.command(name="phone", description="Access your communication device and network hub (Smartphone, Cyberdeck, Comms Pad)")
    async def phone_cmd(self, interaction: discord.Interaction):
        await self._do_hub(interaction)

    async def _do_hub(self, interaction: discord.Interaction):
        char = await adb(db.get_character, interaction.user.id)
        if not char:
            await interaction.response.send_message(
                "You need a character first. Use `/character create`.", ephemeral=True
            )
            return

        session_id = await adb(db.get_active_session_id_for_user, interaction.user.id)
        if not session_id:
            await interaction.response.send_message(
                "No active adventure. Start one with `/adventure start` or `/adventure custom`.", ephemeral=True
            )
            return

        session = await adb(db.get_session, session_id)
        if not session or session["status"] != "active":
            await interaction.response.send_message(
                "No active adventure session found.", ephemeral=True
            )
            return

        scen_key = session.get("scenario", "fantasy")
        from mechanics.system.phone import scenario_has_smartphone, build_phone_home_embed, PhoneMainView
        if not scenario_has_smartphone(scen_key):
            await interaction.response.send_message(
                "❌ Your current scenario does not feature a personal device or communication hub.",
                ephemeral=True
            )
            return

        from mechanics.combat import is_in_combat
        if is_in_combat(session):
            await interaction.response.send_message(
                "❌ You cannot access your communication device while engaged in combat!",
                ephemeral=True
            )
            return

        embed = build_phone_home_embed(session_id, interaction.user.id)
        view = PhoneMainView(self, session_id, interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


    adventure_group = app_commands.Group(name="adventure", description="Play Hikayat")

    @adventure_group.command(name="resume", description="Resume your active adventure session")
    async def adventure_resume(self, interaction: discord.Interaction):
        await self._do_resume(interaction)

    @adventure_group.command(name="map", description="View the World Map and explore discovered regions")
    async def adventure_map(self, interaction: discord.Interaction):
        await self._do_map(interaction)

    @adventure_group.command(name="hub", description="Access your communication device and network hub (Smartphone, Cyberdeck, Comms Pad)")
    async def adventure_hub(self, interaction: discord.Interaction):
        await self._do_hub(interaction)

    @adventure_group.command(name="start", description="Begin a new adventure")
    @app_commands.describe(mode="Solo or multiplayer",
                           scenario="Pick a preset scenario or select Custom Scenario",
                           tags="Comma-separated tags (Required only if scenario is set to Custom)",
                           verbosity="Override your default narration style for this adventure",
                           dialogue="Override your default dialogue setting for this adventure",
                           image_generation="Override your default image-generation setting for this adventure")
    @app_commands.choices(
        mode=[app_commands.Choice(name="Solo", value="solo"),
              app_commands.Choice(name="Multiplayer (Turn-based, 2 players)", value="turn"),
              app_commands.Choice(name="Multiplayer (Synchronized, 2 players)", value="sync")],
        scenario=_scenario_command_choices(),
        verbosity=[app_commands.Choice(name="Shakespearean", value="shakespearean"),
                   app_commands.Choice(name="Vivid", value="vivid"),
                   app_commands.Choice(name="Normal", value="normal"),
                   app_commands.Choice(name="Direct", value="direct"),
                   app_commands.Choice(name="Concise", value="concise")],
        dialogue=[app_commands.Choice(name="Off", value="off"),
                  app_commands.Choice(name="Minimal", value="minimal"),
                  app_commands.Choice(name="Balanced", value="balanced"),
                  app_commands.Choice(name="Adaptive", value="adaptive"),
                  app_commands.Choice(name="Rich", value="rich")],
        image_generation=[app_commands.Choice(name="On", value="on"),
                          app_commands.Choice(name="Off", value="off")],
    )
    async def start(self, interaction: discord.Interaction, mode: app_commands.Choice[str],
                     scenario: app_commands.Choice[str] = None,
                     tags: str = None,
                     verbosity: app_commands.Choice[str] = None,
                     dialogue: app_commands.Choice[str] = None,
                     image_generation: app_commands.Choice[str] = None):
        char = await adb(db.get_character, interaction.user.id)
        if not char:
            await interaction.response.send_message(
                "You need a character first. Use `/character create`.", ephemeral=True)
            return

        existing_id = await adb(db.get_active_session_id_for_user, interaction.user.id)
        if existing_id:
            session = await adb(db.get_session, existing_id)
            if session and session["status"] == "active":
                await interaction.response.defer()
                await self._resend_current_scene(interaction, session, use_followup=True)
                return
            elif session and session["status"] == "waiting":
                await interaction.response.send_message(
                    "You're already waiting for a second player in another game.", ephemeral=True)
                return

        settings = await adb(db.get_settings, interaction.user.id)
        effective_verbosity = verbosity.value if verbosity else settings["verbosity"]
        effective_dialogue = dialogue.value if dialogue else settings.get("dialogue_mode", "balanced")
        effective_image_gen = (image_generation.value == "on") if image_generation else bool(
            settings["image_gen_enabled"])
        effective_result_display = settings.get("result_display", "detailed")

        from scenario_data import resolve_scenario_or_custom_key, resolve_scenario_key, get_scenario
        scen_val = scenario.value if scenario else "fantasy"
        if scen_val == "custom":
            if not tags:
                await interaction.response.send_message(
                    "You selected 'Custom Scenario', but didn't enter any tags! Please enter your tags in the `tags` parameter (e.g. `cyberpunk, nsfw`).",
                    ephemeral=True
                )
                return
            effective_scenario = resolve_scenario_or_custom_key(tags)
        else:
            effective_scenario = resolve_scenario_key(scen_val)

        scen_info = get_scenario(effective_scenario)
        scenario_label = scen_info.get("name", effective_scenario)

        session_config = {
            "mode": mode.value,
            "scenario": effective_scenario,
            "verbosity": effective_verbosity,
            "dialogue": effective_dialogue,
            "image_gen": effective_image_gen,
            "choices_style": "dropdown",
            "result_display": effective_result_display,
        }

        if mode.value == "solo":
            view = LoadoutClassSelectView(self, interaction.user.id, session_config)
            await interaction.response.send_message(
                content=f"🌟 Starting adventure in **{scenario_label}**!\nChoose your profession:",
                view=view, ephemeral=True
            )
        else:
            capacity = 2
            session_id = await adb(db.create_session, interaction.user.id, mode.value, capacity,
                                            effective_verbosity, effective_dialogue, effective_image_gen,
                                            "dropdown", interaction.channel_id,
                                            scenario=effective_scenario,
                                            result_display=effective_result_display)
            await interaction.response.send_message(
                content=(f"**{char['name']}** is looking for a second adventurer for "
                         f"**{MODE_LABELS[mode.value]}** play in **{scenario_label}**! "
                         f"Click below to join."),
                view=JoinView(self, session_id))

    @start.autocomplete("tags")
    async def start_tags_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        from scenario_data import load_tags
        import re
        try:
            tags_dict = load_tags()
        except Exception:
            tags_dict = {}

        cleaned_current = re.sub(r"\(.*?\)", "", current or "")
        parts = [p.strip() for p in cleaned_current.split(",")]
        
        if cleaned_current.endswith(","):
            prefix = ", ".join(p for p in parts if p) + ", " if any(parts) else ""
            last_part = ""
            already_selected = set(p.lower() for p in parts if p)
        else:
            prefix = ", ".join(p for p in parts[:-1] if p) + ", " if len(parts) > 1 else ""
            last_part = parts[-1].lower() if parts else ""
            already_selected = set(p.lower() for p in parts[:-1] if p)

        choices = []
        for tag_key, tag_info in tags_dict.items():
            if tag_key.lower() in already_selected:
                continue
            display_name = tag_info.get("name", tag_key)
            if not last_part or last_part in tag_key.lower() or last_part in display_name.lower():
                val = f"{prefix}{tag_key}"
                label = f"{prefix}+ {display_name}" if prefix else f"{display_name} ({tag_key})"
                if len(label) > 100:
                    label = label[:97] + "..."
                if len(val) > 100:
                    continue
                choices.append(app_commands.Choice(name=label, value=val))
                if len(choices) >= 25:
                    break

        return choices

    async def _resend_current_scene(self, interaction: discord.Interaction, session: dict, use_followup: bool):
        party = list(await asyncio.gather(
            *[(asyncio.gather(adb(db.get_character, uid), adb(db.get_inventory, uid)))
              for uid in session["turn_order"]]
        ))
        scen_key = session.get("scenario", "fantasy")
        first_char = party[0][0] if party and party[0] else None

        if not session.get("choices"):
            location = session.get("current_location", "")
            choices = self._clean_choices([], scenario=scen_key, location=location, char=first_char, session_id=session.get("id"))
            session["choices"] = choices
            try:
                await adb(db.save_session_scene,
                    session["id"],
                    session.get("scene_title") or "Adventure Continues",
                    session.get("narrative") or "You look around and assess your surroundings before taking action.",
                    choices,
                    session.get("history") or []
                )
            except Exception:
                pass

        if not session.get("scene_title"):
            session["scene_title"] = "Adventure Continues"
        if not session.get("narrative"):
            session["narrative"] = "You look around and assess your surroundings before taking action."

        if session["mode"] == "sync":
            waiting_on = [uid for uid in session["turn_order"] if str(uid) not in session["pending_picks"]]
            embeds = sync_scene_embed(session, party, session["scene_title"], session["narrative"],
                                      session["choices"], waiting_on)
            view = SyncChoiceView(self, session["id"], session["turn_order"], session["choices"], party,
                                   session.get("merchant"))
        else:
            turn_uid = db.current_turn_user_id(session)
            actor_char = await adb(db.get_character, turn_uid)
            embeds = scene_embed(session, actor_char, session["scene_title"], session["narrative"],
                                 session["choices"])
            view = ChoiceView(self, session["id"], turn_uid, session["choices"], actor_char,
                               session.get("merchant"))
        target_channel = interaction.channel or self.bot.get_channel(session.get("channel_id"))
        sent = False
        if use_followup:
            try:
                await interaction.followup.send(content="Resuming your adventure...", embeds=embeds, view=view)
                sent = True
            except (discord.NotFound, discord.HTTPException) as e:
                logger.warning("interaction.followup.send failed (%s), falling back to channel.send", e)
        if not sent:
            if target_channel:
                await target_channel.send(content="Resuming your adventure...", embeds=embeds, view=view)
            else:
                await interaction.followup.send(content="Resuming your adventure...", embeds=embeds, view=view)

    async def launch_opening_scene(self, interaction: discord.Interaction, session: dict,
                                    use_followup: bool = False):
        party = list(await asyncio.gather(
            *[(asyncio.gather(adb(db.get_character, uid), adb(db.get_inventory, uid)))
              for uid in session["turn_order"]]
        ))
        scen_key = session.get("scenario", "fantasy")
        from mechanics.social.factions import ensure_session_factions_seeded
        ensure_session_factions_seeded(session["id"], scen_key)
        from mechanics.world.world_forge.seeder import forge_world_state
        await forge_world_state(session, party)
        try:
            scene = await game_engine.generate_opening_scene(session, party)
            # Safety coercion: generate_opening_scene returns dict; guard against any Pydantic leaks
            if getattr(scene, "model_dump", None):
                scene = scene.model_dump(exclude_unset=False)
            if not isinstance(scene, dict):
                scene = {}
        except Exception as e:
            logger.error("Failed to generate opening scene for session %s: %s", session.get("id"), e, exc_info=True)
            try:
                await adb(db.finish_session, session["id"])
            except Exception:
                pass
            msg = f"⚠️ The LLM failed to generate a scene: {e}\n\nThe session could not be started and was closed. Please try `/adventure start` again."
            target_channel = interaction.channel or self.bot.get_channel(session.get("channel_id"))
            if use_followup:
                try:
                    await interaction.followup.send(msg)
                except (discord.NotFound, discord.HTTPException):
                    if target_channel:
                        await target_channel.send(msg)
            elif target_channel:
                await target_channel.send(msg)
            return
        first_char = party[0][0] if party and party[0] else None
        raw_choices, narrative, scene_title, partner_arg, npcs = game_engine.extract_scene_fields(scene)
        location = scene.get("location", "")
        enemies = scene.get("nearby_enemies", [])
        choices = self._clean_choices(raw_choices, scenario=scen_key, location=location, char=first_char, dialogue_partner=partner_arg, current_npcs=npcs, session_id=session.get("id"))
        await adb(db.save_session_scene, session["id"], scene_title,
                               narrative, choices, history=[],
                               location=location, nearby_enemies=enemies, current_npcs=npcs,
                               dialogue_partner=partner_arg)
        merchant = _apply_merchant_encounter_result(session["id"], scene.get("merchant_encounter"))
        scen_key = session.get("scenario", "fantasy")
        first_char_id = party[0][0]["id"] if party and party[0][0] else 0
        for entity in scene.get("new_entities", []) or []:
            ent_type = entity.get("type", "person")
            ent_name = entity.get("name", "")
            raw_race = entity.get("race") or "" if ent_type.lower() == "person" else ""
            norm_race = normalize_race(raw_race, scen_key=scen_key) if raw_race else raw_race
            raw_app = entity.get("appearance", {}) if ent_type.lower() == "person" else {}
            gender = entity.get("gender", "")
            norm_app = normalize_appearance(raw_app, gender=gender, race=norm_race or "human", scen_key=scen_key)

            disp_val = str(entity.get("disposition", "neutral")).lower()
            await adb(db.upsert_lorebook_entity,
                session["id"],
                ent_type,
                ent_name,
                entity.get("description", ""),
                disp_val,
                faction=entity.get("faction", ""),
                traits=entity.get("traits", []),
                motivation=entity.get("motivation", ""),
                mannerisms=entity.get("mannerisms", ""),
                race=norm_race,
                appearance=norm_app,
            )
            if ent_type.lower() == "person" and ent_name:
                await adb(db.upsert_contact,
                    session_id=session["id"],
                    character_id=first_char_id,
                    npc_id=ent_name,
                    name=ent_name,
                    basic_info={"description": entity.get("description", ""), "role": entity.get("role", "")},
                    delta_score=0,
                    new_traits=entity.get("traits", []),
                    new_preferences=entity.get("preferences", []),
                    race=norm_race,
                    gender=gender,
                    appearance=norm_app,
                )

        enemy_names = {game_engine._get_npc_name(e).lower() for e in enemies if e}
        for npc in (npcs or []):
            n_name = game_engine._get_npc_name(npc)
            if n_name and n_name.lower() not in enemy_names:
                await adb(db.upsert_contact,
                    session_id=session["id"],
                    character_id=first_char_id,
                    npc_id=n_name,
                    name=n_name,
                    basic_info={"role": npc.get("role", "") if isinstance(npc, dict) else ""},
                    delta_score=0,
                    race=npc.get("race", "") if isinstance(npc, dict) else "",
                    gender=npc.get("gender", "") if isinstance(npc, dict) else "",
                    appearance=npc.get("appearance", {}) if isinstance(npc, dict) else None,
                )

        fresh_session = await adb(db.get_session, session["id"])
        image_url = await self._maybe_generate_image(fresh_session, scene.get("image_prompt"))

        if session["mode"] == "sync":
            embeds = sync_scene_embed(fresh_session, party, scene.get("scene_title"), narrative,
                                      choices, waiting_on=[], image_url=image_url)
            view = SyncChoiceView(self, session["id"], fresh_session["turn_order"], choices, party, merchant)
        else:
            turn_uid = db.current_turn_user_id(fresh_session)
            actor_char = await adb(db.get_character, turn_uid)
            embeds = scene_embed(fresh_session, actor_char, scene.get("scene_title"), narrative,
                                 choices, image_url)
            view = ChoiceView(self, session["id"], turn_uid, choices, actor_char, merchant)

        target_channel = interaction.channel or self.bot.get_channel(session.get("channel_id"))
        sent = False
        if use_followup:
            try:
                await interaction.followup.send(embeds=embeds, view=view)
                sent = True
            except (discord.NotFound, discord.HTTPException) as e:
                logger.warning("interaction.followup.send failed (%s), falling back to channel.send", e)
        if not sent:
            if target_channel:
                await target_channel.send(embeds=embeds, view=view)
            else:
                await interaction.followup.send(embeds=embeds, view=view)

    async def _maybe_generate_image(self, session: dict, image_prompt: str | None) -> str | None:
        if not session.get("image_gen_enabled"):
            return None
        prompt = (image_prompt or "").strip()
        if not prompt:
            scenario = session.get("scenario", "fantasy")
            location = session.get("current_location") or session.get("scene_title") or ""
            narrative = (session.get("narrative") or "")[:450]
            if narrative or location:
                prompt = f"{scenario} RPG scene illustration. Location: {location}. {narrative}".strip()
        if not prompt:
            return None

        model_override = None
        host_uid = session.get("host_user_id")
        if host_uid:
            try:
                user_settings = await adb(db.get_settings, host_uid)
                model_override = user_settings.get("image_model") or None
            except Exception:
                pass

        try:
            return await image_client.generate_scene_image(prompt, model=model_override)
        except Exception as e:
            logger.warning("Scene image generation failed for session %s: %s", session.get("id"), e)
            return None

    @staticmethod
    def _safe_int(val, default: int = 0) -> int:
        if val is None:
            return default
        try:
            if isinstance(val, (int, float)):
                return int(val)
            val_str = str(val).strip()
            if not val_str:
                return default
            return int(float(val_str))
        except (ValueError, TypeError):
            return default

    STAT_FALLBACK_LABELS = {
        "STR": "Exert physical strength",
        "AGI": "Attempt a swift movement",
        "END": "Brace and endure the situation",
        "INT": "Analyze the situation carefully",
        "PER": "Observe the surroundings",
        "CHA": "Speak with someone nearby",
        "LUK": "Take a spontaneous chance",
    }

    # Keywords that mark high-value narrative information we must try to keep.
    _HIGH_VALUE_KEYWORDS = (
        "killed", "died", "defeated", "completed", "failed", "discovered",
        "revealed", "betrayed", "promised", "agreed", "refused", "escaped",
        "arrived", "left", "joined", "recruited", "unlocked", "obtained",
        "found", "lost", "broke", "healed", "opened", "entered", "exited",
    )

    @staticmethod
    def _compact_summary(text: str, max_chars: int = 500) -> str:
        """Distil a long outcome narrative into a compact, information-dense
        history entry using semantic preservation instead of hard truncation.

        Strategy (in priority order):
          1. If text fits within max_chars, return it unchanged.
          2. Split into sentences. Score each by presence of proper nouns
             (Title Case words), quest/outcome verbs, and dialogue markers.
          3. Greedily select the highest-scoring sentences until max_chars.
          4. Re-join in original sentence order for readability.
        """
        import re
        text = (text or "").strip()
        if len(text) <= max_chars:
            return text

        # Sentence tokenisation (simple but robust)
        raw_sentences = re.split(r'(?<=[.!?"])\s+', text)
        sentences = [s.strip() for s in raw_sentences if s.strip()]
        if not sentences:
            return text[:max_chars] + "…"

        # Scoring heuristics
        high_value = AdventureCog._HIGH_VALUE_KEYWORDS
        _PROPER_RE = re.compile(r'\b[A-Z][a-z]{2,}\b')

        def _score(s: str) -> float:
            score = 0.0
            s_lower = s.lower()
            # Proper nouns (names, places) are very valuable
            score += len(_PROPER_RE.findall(s)) * 2.0
            # Outcome verbs
            score += sum(1.5 for kw in high_value if kw in s_lower)
            # Dialogue (quotes) — preserves NPC voice
            score += s.count('"') * 0.8 + s.count("'") * 0.4
            # Slightly penalise very short sentences (filler)
            score -= max(0, (20 - len(s)) * 0.05)
            return score

        scored = [(i, _score(s), s) for i, s in enumerate(sentences)]
        scored.sort(key=lambda x: -x[1])  # descending by score

        # Greedy selection up to max_chars
        selected_indices: set[int] = set()
        total = 0
        for idx, _sc, s in scored:
            if total + len(s) + 1 <= max_chars:
                selected_indices.add(idx)
                total += len(s) + 1
            if total >= max_chars * 0.9:
                break

        # Always include the first sentence (scene grounding)
        selected_indices.add(0)

        # Re-join in original order
        result = " ".join(sentences[i] for i in sorted(selected_indices))
        return result if len(result) <= max_chars + 20 else result[:max_chars].rsplit(" ", 1)[0] + "…"

    @classmethod
    def _clean_choices(cls, choices: list, scenario: str = "fantasy", location: str = "", char: dict = None, dialogue_partner: str = None, current_npcs: list = None, session_id: int = None) -> list:
        from .choices_cleaner import clean_choices_impl
        return clean_choices_impl(cls, choices, scenario, location, char, dialogue_partner, current_npcs, session_id)
    def _apply_xp(self, user_id: int, check: CheckResult):
        """Awards XP for this action's outcome tier. XP-driven leveling
        (db.add_xp) is the ONLY way a character gains stat points -- there is
        intentionally no passive stat growth from repeated stat use."""
        xp_gain = XP_REWARDS.get(check.tier, 0)
        levels_gained = db.add_xp(user_id, xp_gain)
        return levels_gained

    @staticmethod
    async def _safe_send(interaction: discord.Interaction, **kwargs):
        """Send via interaction.followup, falling back to interaction.channel.send
        if the 15-minute followup token has expired (HTTP 401 / error 50027).
        This prevents uncaught exceptions when players wait a long time before
        clicking a choice or when the LLM takes unusually long."""
        if "wait" not in kwargs and "view" in kwargs:
            kwargs["wait"] = True
        try:
            return await interaction.followup.send(**kwargs)
        except (discord.HTTPException, discord.NotFound) as exc:
            # 401 (50027) = Invalid/expired webhook token, 404 (10062) = Unknown interaction
            if getattr(exc, "code", None) in (50027, 10062) or (hasattr(exc, "status") and exc.status in (401, 404)):
                logger.warning("Followup token expired or invalid (%s), falling back to channel.send", exc)
                # Remove webhook-only arguments — channel.send does not support them
                kwargs.pop("ephemeral", None)
                kwargs.pop("wait", None)
                channel = interaction.channel
                if channel:
                    return await channel.send(**kwargs)
                raise
            else:
                raise

    async def _announce_levelup(self, interaction: discord.Interaction, user_id: int, levels_gained: list):
        if not levels_gained:
            return
        char = db.get_character(user_id)
        text = f"🎉 <@{user_id}>'s **{char['name']}** reached level **{levels_gained[-1]}**!"
        if char["level"] >= MAX_LEVEL:
            text += " (max level reached)"
        if char["pending_stat_points"] > 0:
            await interaction.channel.send(
                content=f"{text} You have **{char['pending_stat_points']}** stat point(s) to spend:",
                view=StatPointView(user_id))
        else:
            await interaction.channel.send(content=text)

    # ------------------------------------------------------------- turn-based
    @adventure_group.command(name="leave", description="Abandon your current adventure")
    async def leave(self, interaction: discord.Interaction):
        session_id = await adb(db.get_active_session_id_for_user, interaction.user.id)
        if not session_id:
            await interaction.response.send_message("You're not in an active adventure.", ephemeral=True)
            return
        await adb(db.finish_session, session_id)
        await interaction.response.send_message("You've left the adventure. Use `/adventure start` or `/adventure custom` to begin a new one.")

    # ---------------------------------------------------------- campaign save slots
    async def _save_slot_autocomplete(self, interaction: discord.Interaction, current: str):
        saves = await adb(db.list_adventure_saves, interaction.user.id)
        current_lower = current.lower()
        choices = []
        for s in saves:
            name = s["slot_name"]
            if current_lower and current_lower not in name.lower():
                continue
            scen = str(s.get("scenario", "fantasy")).title()
            title = (s.get("scene_title") or "Adventure")[:30]
            label = f"{name} [{scen} - {title}]"
            choices.append(app_commands.Choice(name=label[:100], value=name))
            if len(choices) >= 25:
                break
        return choices

    @adventure_group.command(name="save", description="Save your active adventure progress to a named checkpoint slot")
    @app_commands.describe(name="Name for your save slot (e.g. Chapter 1, Before Boss, Castle Gate)")
    async def save_slot_cmd(self, interaction: discord.Interaction, name: str):
        from mechanics.system.save_system import validate_slot_name, OverwriteConfirmView
        try:
            clean_name = validate_slot_name(name)
        except ValueError as e:
            await interaction.response.send_message(f"❌ {e}", ephemeral=True)
            return

        session_id = await adb(db.get_active_session_id_for_user, interaction.user.id)
        if not session_id:
            await interaction.response.send_message("❌ You're not in an active adventure to save.", ephemeral=True)
            return

        try:
            res = await adb(db.save_adventure_slot, interaction.user.id, clean_name, overwrite=False)
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed to save: {e}", ephemeral=True)
            return

        if res.get("status") == "exists":
            view = OverwriteConfirmView(self, interaction.user.id, clean_name)
            await interaction.response.send_message(res["message"], view=view, ephemeral=True)
            return

        loc = res.get("current_location") or "Wilderness"
        await interaction.response.send_message(
            f"💾 Successfully saved adventure checkpoint **{res['slot_name']}** at location **{loc}**!\n"
            f"You can restore this checkpoint anytime using `/adventure load {res['slot_name']}` or browse with `/adventure saves`.",
            ephemeral=True
        )

    @adventure_group.command(name="load", description="Load a saved adventure checkpoint")
    @app_commands.describe(name="The name of the save slot to restore")
    async def load_slot_cmd(self, interaction: discord.Interaction, name: str):
        from mechanics.system.save_system import LoadConfirmView
        clean_name = (name or "").strip()
        save_meta = await adb(db.get_adventure_save_metadata, interaction.user.id, clean_name)
        if not save_meta:
            await interaction.response.send_message(
                f"❌ Save slot '{clean_name}' not found. Use `/adventure saves` to view all your checkpoints.",
                ephemeral=True
            )
            return

        active_id = await adb(db.get_active_session_id_for_user, interaction.user.id)
        if active_id:
            view = LoadConfirmView(self, interaction.user.id, clean_name)
            await interaction.response.send_message(
                f"⚠️ You currently have an active adventure in progress! Loading checkpoint **{clean_name}** "
                f"will replace your current active adventure. Do you want to proceed?",
                view=view,
                ephemeral=True
            )
            return

        await interaction.response.defer()
        try:
            session = await adb(db.load_adventure_slot, interaction.user.id, clean_name)
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to load save slot: {e}", ephemeral=True)
            return

        await interaction.followup.send(f"✅ Successfully loaded checkpoint **{clean_name}**!")
        await self._resend_current_scene(interaction, session, use_followup=True)

    @load_slot_cmd.autocomplete("name")
    async def load_slot_autocomplete(self, interaction: discord.Interaction, current: str):
        return await self._save_slot_autocomplete(interaction, current)

    @adventure_group.command(name="saves", description="Browse and manage your saved adventure checkpoints")
    async def list_saves_cmd(self, interaction: discord.Interaction):
        from mechanics.system.save_system import build_saves_list_embed, SaveManagerView
        char = await adb(db.get_character, interaction.user.id)
        if not char:
            await interaction.response.send_message("❌ You don't have an active character. Create one with `/character create` first.", ephemeral=True)
            return

        saves = await adb(db.list_adventure_saves, interaction.user.id)
        embed = build_saves_list_embed(saves, char)
        view = SaveManagerView(self, interaction.user.id, saves)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @adventure_group.command(name="delete_save", description="Permanently delete an adventure save slot")
    @app_commands.describe(name="The name of the save slot to delete")
    async def delete_save_cmd(self, interaction: discord.Interaction, name: str):
        from mechanics.system.save_system import DeleteSaveConfirmView
        clean_name = (name or "").strip()
        save_meta = await adb(db.get_adventure_save_metadata, interaction.user.id, clean_name)
        if not save_meta:
            await interaction.response.send_message(f"❌ Save slot '{clean_name}' not found.", ephemeral=True)
            return

        view = DeleteSaveConfirmView(self, interaction.user.id, clean_name)
        await interaction.response.send_message(
            f"⚠️ Are you sure you want to permanently delete save slot **{clean_name}**? This cannot be undone.",
            view=view,
            ephemeral=True
        )

    @delete_save_cmd.autocomplete("name")
    async def delete_save_autocomplete(self, interaction: discord.Interaction, current: str):
        return await self._save_slot_autocomplete(interaction, current)



async def setup(bot: commands.Bot):
    await bot.add_cog(AdventureCog(bot))
