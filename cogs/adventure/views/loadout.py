from .constants import *
import random
import discord
import db
from db import adb
from character_data import (
    STATS,
    STAT_NAMES,
    STAT_EMOJI,
    MAX_STAT_VALUE,
    get_class_templates,
    get_starting_weapons,
    get_starter_gear_by_class,
    get_starting_items,
)
from cogs.character import build_character_sheet_embed
from db import STAT_COLUMN
from mechanics.social.persona import (
    FEMALE_ASSET_TEXTURES,
    FEMALE_TIER_INCOMPATIBLE_TEXTURES,
    MALE_ASSET_TEXTURES,
    MALE_TIER_INCOMPATIBLE_TEXTURES,
    REAR_ASSET_TEXTURES,
    REAR_TIER_INCOMPATIBLE_TEXTURES,
    classify_asset_size_tier,
    classify_rear_size_tier,
    get_species_surface_profile,
    heal_rear_texture_for_context,
    is_feral_rear_excluded,
    is_male_gender,
    normalize_asset_texture,
    normalize_rear_texture,
    roll_dynamic_asset_texture,
    roll_dynamic_rear_texture,
)

class StatPointView(discord.ui.View):
    """Shown when a character has unspent stat points from leveling up.
    Works both as a standalone `/character levelup` response and as an
    auto-posted announcement after a turn resolves."""

    def __init__(self, user_id: int, char: dict | None = None):
        super().__init__(timeout=600)
        self.user_id = user_id
        if char is None:
            char = db.get_character(user_id)
        for stat in STATS:
            at_cap = bool(char) and char[STAT_COLUMN[stat]] >= MAX_STAT_VALUE
            button = discord.ui.Button(
                label=f"{STAT_NAMES[stat]} (MAX)" if at_cap else STAT_NAMES[stat],
                emoji=STAT_EMOJI[stat],
                style=discord.ButtonStyle.secondary, custom_id=f"lvl_{stat}",
                disabled=at_cap)
            button.callback = self._make_callback(stat)
            self.add_item(button)

    def _make_callback(self, stat: str):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.user_id:
                await interaction.response.send_message("These points aren't yours to spend.",
                                                          ephemeral=True)
                return
            result = await adb(db.spend_stat_point, self.user_id, stat)

            if result == "no_points":
                for child in self.children:
                    child.disabled = True
                await interaction.response.edit_message(
                    content="All stat points have been spent!", view=self)
                self.stop()
                return

            if result == "capped":
                await interaction.response.send_message(
                    f"**{STAT_NAMES[stat]}** is already at the maximum ({MAX_STAT_VALUE}) -- "
                    f"choose a different stat.", ephemeral=True)
                return

            char = await adb(db.get_character, self.user_id)
            remaining = char["pending_stat_points"]
            content = f"**{STAT_NAMES[stat]}** increased to {char[STAT_COLUMN[stat]]}! "

            # Re-disable any button(s) that just hit the cap, and stop
            # offering points once none remain unspent.
            all_capped = True
            for child in self.children:
                child_stat = child.custom_id.removeprefix("lvl_")
                if char[STAT_COLUMN[child_stat]] >= MAX_STAT_VALUE:
                    child.disabled = True
                    child.label = f"{STAT_NAMES[child_stat]} (MAX)"
                else:
                    all_capped = False

            if remaining > 0 and not all_capped:
                content += f"You have **{remaining}** point(s) left to spend:"
                await interaction.response.edit_message(content=content, view=self)
            else:
                if remaining > 0 and all_capped:
                    content += (f"You still have **{remaining}** point(s), but every stat is "
                                f"already at the maximum ({MAX_STAT_VALUE}) -- nowhere left to put them.")
                else:
                    content += "All points spent!"
                for child in self.children:
                    child.disabled = True
                await interaction.response.edit_message(content=content, view=self)
                self.stop()
        return callback

class LoadoutCustomClassModal(discord.ui.Modal, title="Describe Your Profession"):
    class_name = discord.ui.TextInput(
        label="Profession / Role Name", placeholder="e.g. Netrunner, Street Samurai, Exorcist", max_length=40
    )
    description = discord.ui.TextInput(
        label="Description & Playstyle", style=discord.TextStyle.paragraph,
        placeholder="What is their background, skillset, quirks, or fighting style?", max_length=300, required=False
    )

    def __init__(self, cog: "AdventureCog", user_id: int, session_config: dict):
        super().__init__()
        self.cog = cog
        self.user_id = user_id
        self.session_config = session_config

    async def on_submit(self, interaction: discord.Interaction):
        c_name = str(self.class_name).strip()
        c_desc = str(self.description).strip()
        scenario = self.session_config.get("scenario", "fantasy")
        from scenario_data import is_non_combat_scenario
        if is_non_combat_scenario(scenario):
            await interaction.response.defer(ephemeral=True)
            view = await LoadoutEquipmentPreviewView.create(
                self.cog, self.user_id, self.session_config, c_name, c_desc, "", ""
            )
            embed = view.build_embed()
            await interaction.followup.send(
                content=f"Chosen Profession: **{c_name}** (Non-Combat)\n⚔️ **Adventure Loadout Preview** — Review your gear before embarking:",
                embed=embed, view=view, ephemeral=True
            )
            return

        from scenario_data import is_anomalous_incursions_scenario
        if is_anomalous_incursions_scenario(scenario):
            view = AnomalousAttunementView(self.cog, self.user_id, self.session_config, c_name, c_desc)
            await interaction.response.send_message(
                content=(
                    f"Chosen Profession: **{c_name}**\n"
                    "🧬 **Step 2: Awakened Resonance Attunement** — Lock your **Attribute**, **Combat Archetype**, and **Ability Medium**:"
                ),
                view=view,
                ephemeral=True,
            )
            return

        view = LoadoutWeaponSelectView(self.cog, self.user_id, self.session_config, c_name, c_desc)
        await interaction.response.send_message(
            content=f"Chosen Profession: **{c_name}**\nNow choose your starting weapon:",
            view=view, ephemeral=True
        )

class LoadoutClassSelectView(discord.ui.View):
    def __init__(self, cog: "AdventureCog", user_id: int, session_config: dict):
        super().__init__(timeout=300)
        self.cog = cog
        self.user_id = user_id
        self.session_config = session_config
        self._build_selects()

    def _build_selects(self):
        self.clear_items()
        scenario = self.session_config.get("scenario", "fantasy")
        from scenario_data import is_anomalous_incursions_scenario
        is_anom = is_anomalous_incursions_scenario(scenario)
        import scenario_data
        is_ahs = scenario_data.is_anomalous_high_school_scenario(scenario)
        current_row = 0
        if is_ahs:
            origin_mode = self.session_config.setdefault("origin_mode", "student")
            student_grade = self.session_config.setdefault("student_grade", "Sophomore")
            origin_select = discord.ui.Select(
                placeholder="Choose Operative Protocol (Student vs Adult)...",
                options=[
                    discord.SelectOption(
                        label="Student Operative (High School & Freelance)",
                        value="student",
                        description="School classes & clubs by day, anomaly hunting by night",
                        default=(origin_mode == "student"),
                    ),
                    discord.SelectOption(
                        label="Adult Field Agent (Full Agency Enlistment)",
                        value="adult",
                        description="Full agency employment with adult clearance & mandates",
                        default=(origin_mode == "adult"),
                    ),
                ],
                row=current_row,
            )
            origin_select.callback = self._on_origin_select
            self.add_item(origin_select)
            current_row += 1

            if origin_mode == "student":
                self.session_config["starting_faction"] = "student_freelancer"
                starting_faction = "student_freelancer"
                grade_select = discord.ui.Select(
                    placeholder="Choose Student Grade Year...",
                    options=[
                        discord.SelectOption(label="Freshman (1st Year)", value="Freshman", default=(student_grade == "Freshman")),
                        discord.SelectOption(label="Sophomore (2nd Year)", value="Sophomore", default=(student_grade == "Sophomore")),
                        discord.SelectOption(label="Junior (3rd Year)", value="Junior", default=(student_grade == "Junior")),
                        discord.SelectOption(label="Senior (4th Year)", value="Senior", default=(student_grade == "Senior")),
                    ],
                    row=current_row,
                )
                grade_select.callback = self._on_grade_select
                self.add_item(grade_select)
                current_row += 1
        starting_faction = self.session_config.get("starting_faction", "public_agency")

        if is_anom and (not is_ahs or self.session_config.get("origin_mode") == "adult"):
            fac_options = [
                discord.SelectOption(
                    label="Public Containment Agency",
                    value="public_agency",
                    description="Daily Salary • 50% HQ Discount • Bureau HQ Start",
                    default=(starting_faction == "public_agency"),
                ),
                discord.SelectOption(
                    label="Corporate Containment Conglomerate",
                    value="private_agency_1",
                    description="Skyscraper Tower HQ • Special Ordnance Vault • Keep 100% Loot",
                    default=(starting_faction == "private_agency_1"),
                ),
                discord.SelectOption(
                    label="Independent Private Agency",
                    value="private_agency_2",
                    description="Partner Field Office HQ • Custom Gunsmith Armory • Keep 100% Loot",
                    default=(starting_faction == "private_agency_2"),
                ),
                discord.SelectOption(
                    label="Monastic Shrine Order",
                    value="monastic_order",
                    description="Free Sacred Shrine Rations • Traditional Exorcist Gear • Grand Temple Start",
                    default=(starting_faction == "monastic_order"),
                ),
                discord.SelectOption(
                    label="Occult Cult",
                    value="cult_faction",
                    description="0.85x Ritual Shop • -50% Pact Tithes • 4 Resonator Charges • Cult Sanctum Start",
                    default=(starting_faction == "cult_faction"),
                ),
                discord.SelectOption(
                    label="Clandestine Syndicate",
                    value="clandestine_faction",
                    description="+35% Bounty Gold • +40% Fence Sell • Signal Wiretap • Syndicate Cellar Start",
                    default=(starting_faction == "clandestine_faction"),
                ),
                discord.SelectOption(
                    label="Independent Freelancer",
                    value="freelancer",
                    description="No Daily Quotas • Street & Improvised Gear • Suburb Home Start",
                    default=(starting_faction == "freelancer"),
                ),
            ]
            fac_select = discord.ui.Select(
                placeholder="Choose starting faction affiliation...",
                options=fac_options,
                row=current_row,
            )
            current_row += 1
            fac_select.callback = self._on_faction_select
            self.add_item(fac_select)

        from character_data import localize_class_template
        user_settings = db.get_settings(self.user_id) if self.user_id else {}
        ui_lang = str((user_settings or {}).get("ui_language") or "en")
        templates = get_class_templates(scenario, starting_faction=starting_faction)
        options = []
        for cls_name, cls_data in list(templates.items())[:24]:
            loc_cls = localize_class_template(cls_name, cls_data, ui_lang) if ui_lang != "en" and isinstance(cls_data, dict) else cls_data
            disp_label = str((loc_cls or {}).get("display_name") or cls_name)[:100]
            desc = str((loc_cls or {}).get("description") or cls_data.get("description", ""))[:100]
            options.append(discord.SelectOption(label=disp_label, value=cls_name, description=desc))

        options.append(discord.SelectOption(
            label="Custom Profession...", value="__custom__", description="Type your own custom class and background"
        ))

        select = discord.ui.Select(
            placeholder=f"Choose a profession ({scenario.title()})...",
            options=options,
            row=min(4, current_row),
        )
        select.callback = self._on_select
        self.add_item(select)

    async def _on_origin_select(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your adventure setup.", ephemeral=True)
            return
        self.session_config["origin_mode"] = interaction.data["values"][0]
        if self.session_config["origin_mode"] == "student":
            self.session_config["starting_faction"] = "student_freelancer"
        else:
            self.session_config["starting_faction"] = "public_agency"
        self._build_selects()
        await interaction.response.edit_message(view=self)

    async def _on_grade_select(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your adventure setup.", ephemeral=True)
            return
        self.session_config["student_grade"] = interaction.data["values"][0]
        self._build_selects()
        await interaction.response.edit_message(view=self)

    async def _on_faction_select(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your adventure setup.", ephemeral=True)
            return
        self.session_config["starting_faction"] = interaction.data["values"][0]
        self._build_selects()
        await interaction.response.edit_message(view=self)

    async def _on_select(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your adventure setup.", ephemeral=True)
            return
        val = interaction.data["values"][0]
        if val == "__custom__":
            await interaction.response.send_modal(LoadoutCustomClassModal(self.cog, self.user_id, self.session_config))
        else:
            scenario = self.session_config.get("scenario", "fantasy")
            starting_faction = self.session_config.get("starting_faction", "public_agency")
            from scenario_data import is_non_combat_scenario
            templates = get_class_templates(scenario, starting_faction=starting_faction)
            cls_desc = templates.get(val, {}).get("description", "")
            if is_non_combat_scenario(scenario):
                await interaction.response.defer()
                view = await LoadoutEquipmentPreviewView.create(
                    self.cog, self.user_id, self.session_config, val, cls_desc, "", ""
                )
                embed = view.build_embed()
                await interaction.edit_original_response(
                    content=f"Chosen Profession: **{val}** (Non-Combat)\n⚔️ **Adventure Loadout Preview** — Review your gear before embarking:",
                    view=view, embed=embed
                )
                return

            from scenario_data import is_anomalous_incursions_scenario
            if is_anomalous_incursions_scenario(scenario):
                view = AnomalousAttunementView(self.cog, self.user_id, self.session_config, val, cls_desc)
                await interaction.response.edit_message(
                    content=(
                        f"Chosen Profession: **{val}**\n"
                        "🧬 **Step 2: Awakened Resonance Attunement** — Lock your **Attribute**, **Combat Archetype**, and **Ability Medium**:"
                    ),
                    view=view,
                    embed=None,
                )
                return

            view = LoadoutWeaponSelectView(self.cog, self.user_id, self.session_config, val, cls_desc)
            await interaction.response.edit_message(
                content=f"Chosen Profession: **{val}**\nNow choose your starting weapon:",
                view=view, embed=None
            )

class AnomalousAttunementView(discord.ui.View):
    """Step 2 of Anomalous Incursions setup: 3-Axis Resonance Attunement (strictly 4 ActionRows <= 5 cap)."""

    def __init__(
        self,
        cog: "AdventureCog",
        user_id: int,
        session_config: dict,
        char_class: str,
        class_description: str = "",
    ):
        super().__init__(timeout=300)
        self.cog = cog
        self.user_id = user_id
        self.session_config = session_config
        self.char_class = char_class
        self.class_description = class_description
        self.session_config.setdefault("attribute", "fire")
        self.session_config.setdefault("combat_archetype", "vanguard")
        self.session_config.setdefault("ability_medium", "direct_manifestation")
        self._build_controls()

    def _build_controls(self):
        self.clear_items()
        from mechanics.combat.spells.awakened_kits import (
            ATTRIBUTE_META,
            ARCHETYPE_META,
            MEDIUM_META,
            MEDIUM_STAT_SYNERGY,
        )

        cur_attr = str(self.session_config.get("attribute") or "fire").lower()
        cur_arch = str(self.session_config.get("combat_archetype") or "vanguard").lower()
        cur_med = str(self.session_config.get("ability_medium") or "direct_manifestation").lower()

        attr_opts = [
            discord.SelectOption(
                label=f"{meta['label']} ({key.title()})",
                value=key,
                emoji=meta["emoji"],
                description=f"Break Payoff: {meta['ailment']}"[:100],
                default=(key == cur_attr),
            )
            for key, meta in ATTRIBUTE_META.items()
        ]
        attr_sel = discord.ui.Select(
            placeholder="Row 1: Choose Locked Resonance Attribute (9)...",
            options=attr_opts,
            row=0,
        )
        attr_sel.callback = self._on_attr_change
        self.add_item(attr_sel)

        arch_descs = {
            "vanguard": "Main DPS • +30% vs Breached • Execution Strikes",
            "catalyst": "Harmony Buffer • +25% Mono-Attr Party Amp • Weakness Implant",
            "breaker": "Poise Disruptor • 1.6x Off-Weakness Stability Shred & Debuffs",
            "warden": "Hume Sustainer • Temp HP Barriers, Healing & Debuff Cleanse",
        }
        arch_opts = [
            discord.SelectOption(
                label=meta["label"],
                value=key,
                description=arch_descs.get(key, meta.get("role_summary", ""))[:100],
                default=(key == cur_arch),
            )
            for key, meta in ARCHETYPE_META.items()
        ]
        arch_sel = discord.ui.Select(
            placeholder="Row 2: Choose Combat Archetype (4)...",
            options=arch_opts,
            row=1,
        )
        arch_sel.callback = self._on_arch_change
        self.add_item(arch_sel)

        med_opts = []
        for key, meta in MEDIUM_META.items():
            syn_stats = " / ".join(MEDIUM_STAT_SYNERGY.get(key, ("INT",)))
            med_opts.append(
                discord.SelectOption(
                    label=meta["label"],
                    value=key,
                    description=f"Stat Synergy: {syn_stats} • {meta.get('flavor') or meta.get('verb', 'Resonance')}"[:100],
                    default=(key == cur_med),
                )
            )
        med_sel = discord.ui.Select(
            placeholder="Row 3: Choose Ability Medium (4)...",
            options=med_opts,
            row=2,
        )
        med_sel.callback = self._on_med_change
        self.add_item(med_sel)

        back_btn = discord.ui.Button(
            label="Back to Profession",
            emoji="⬅️",
            style=discord.ButtonStyle.secondary,
            row=3,
        )
        back_btn.callback = self._on_back
        self.add_item(back_btn)

        confirm_btn = discord.ui.Button(
            label="Confirm Attunement & Choose Weapon",
            emoji="✅",
            style=discord.ButtonStyle.success,
            row=3,
        )
        confirm_btn.callback = self._on_confirm
        self.add_item(confirm_btn)

    async def _on_attr_change(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your adventure setup.", ephemeral=True)
            return
        self.session_config["attribute"] = interaction.data["values"][0]
        self._build_controls()
        await interaction.response.edit_message(view=self)

    async def _on_arch_change(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your adventure setup.", ephemeral=True)
            return
        self.session_config["combat_archetype"] = interaction.data["values"][0]
        self._build_controls()
        await interaction.response.edit_message(view=self)

    async def _on_med_change(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your adventure setup.", ephemeral=True)
            return
        self.session_config["ability_medium"] = interaction.data["values"][0]
        self._build_controls()
        await interaction.response.edit_message(view=self)

    async def _on_back(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your adventure setup.", ephemeral=True)
            return
        prev_view = LoadoutClassSelectView(self.cog, self.user_id, self.session_config)
        await interaction.response.edit_message(
            content="Choose your starting faction and profession:",
            view=prev_view,
            embed=None,
        )

    async def _on_confirm(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your adventure setup.", ephemeral=True)
            return
        attr = self.session_config.get("attribute", "fire")
        arch = self.session_config.get("combat_archetype", "vanguard")
        med = self.session_config.get("ability_medium", "direct_manifestation")
        view = LoadoutWeaponSelectView(
            self.cog,
            self.user_id,
            self.session_config,
            self.char_class,
            self.class_description,
        )
        await interaction.response.edit_message(
            content=(
                f"Chosen Profession: **{self.char_class}** | "
                f"Resonance: **{attr.title()} • {arch.title()} • {med.replace('_', ' ').title()}**\n"
                "Now choose your starting weapon:"
            ),
            view=view,
            embed=None,
        )


class TelemetryCalibrationView(discord.ui.View):
    """Tier 4+ HQ Telemetry Calibration view (strictly 4 ActionRows <= 5 cap)."""

    def __init__(
        self,
        cog,
        user_id: int,
        session_id: int,
        faction_id: str,
        current_3axis: dict | None = None,
    ):
        super().__init__(timeout=300)
        self.cog = cog
        self.user_id = user_id
        self.session_id = session_id
        self.faction_id = faction_id
        cur = current_3axis or {}
        self.attribute = str(cur.get("attribute") or "fire").lower()
        self.combat_archetype = str(cur.get("combat_archetype") or "vanguard").lower()
        self.ability_medium = str(cur.get("ability_medium") or "direct_manifestation").lower()
        self._build_items()

    def _build_items(self):
        self.clear_items()
        from mechanics.combat.spells.awakened_kits import ATTRIBUTE_META, ARCHETYPE_META, MEDIUM_META

        attr_sel = discord.ui.Select(
            placeholder="Choose Recalibrated Attribute (9)...",
            options=[
                discord.SelectOption(
                    label=f"{m['label']} ({k.title()})",
                    value=k,
                    emoji=m["emoji"],
                    default=(k == self.attribute),
                )
                for k, m in ATTRIBUTE_META.items()
            ],
            row=0,
        )
        attr_sel.callback = self._on_attr
        self.add_item(attr_sel)

        arch_sel = discord.ui.Select(
            placeholder="Choose Recalibrated Archetype (4)...",
            options=[
                discord.SelectOption(label=m["label"], value=k, default=(k == self.combat_archetype))
                for k, m in ARCHETYPE_META.items()
            ],
            row=1,
        )
        arch_sel.callback = self._on_arch
        self.add_item(arch_sel)

        med_sel = discord.ui.Select(
            placeholder="Choose Recalibrated Medium (4)...",
            options=[
                discord.SelectOption(label=m["label"], value=k, default=(k == self.ability_medium))
                for k, m in MEDIUM_META.items()
            ],
            row=2,
        )
        med_sel.callback = self._on_med
        self.add_item(med_sel)

        confirm_btn = discord.ui.Button(
            label="Calibrate (500G + 1x Hume Core)",
            emoji="🧬",
            style=discord.ButtonStyle.success,
            row=3,
        )
        confirm_btn.callback = self._on_confirm
        self.add_item(confirm_btn)

        cancel_btn = discord.ui.Button(
            label="Cancel",
            emoji="✖️",
            style=discord.ButtonStyle.secondary,
            row=3,
        )
        cancel_btn.callback = self._on_cancel
        self.add_item(cancel_btn)

    async def _on_attr(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your calibration session.", ephemeral=True)
            return
        self.attribute = interaction.data["values"][0]
        self._build_items()
        await interaction.response.edit_message(view=self)

    async def _on_arch(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your calibration session.", ephemeral=True)
            return
        self.combat_archetype = interaction.data["values"][0]
        self._build_items()
        await interaction.response.edit_message(view=self)

    async def _on_med(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your calibration session.", ephemeral=True)
            return
        self.ability_medium = interaction.data["values"][0]
        self._build_items()
        await interaction.response.edit_message(view=self)

    async def _on_confirm(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your calibration session.", ephemeral=True)
            return
        await self.cog.faction_calibrate(
            interaction,
            self.session_id,
            self.user_id,
            self.faction_id,
            self.attribute,
            self.combat_archetype,
            self.ability_medium,
        )

    async def _on_cancel(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your calibration session.", ephemeral=True)
            return
        await interaction.response.edit_message(content="Telemetry Calibration cancelled.", view=None)


class LoadoutCustomWeaponModal(discord.ui.Modal, title="Name Your Starting Weapon"):
    weapon_name = discord.ui.TextInput(
        label="Weapon Name", placeholder="e.g. Smart-Linked SMG, Cursed Katana", max_length=60
    )
    weapon_desc = discord.ui.TextInput(
        label="Weapon Description (optional)", style=discord.TextStyle.paragraph,
        placeholder="Flavor details -- appearance, modifications, or material", max_length=200, required=False
    )

    def __init__(self, cog: "AdventureCog", user_id: int, session_config: dict, char_class: str, class_description: str):
        super().__init__()
        self.cog = cog
        self.user_id = user_id
        self.session_config = session_config
        self.char_class = char_class
        self.class_description = class_description

    async def on_submit(self, interaction: discord.Interaction):
        w_name = str(self.weapon_name).strip()
        w_desc = str(self.weapon_desc).strip()
        await interaction.response.defer(ephemeral=True)
        view = await LoadoutEquipmentPreviewView.create(
            self.cog, self.user_id, self.session_config, self.char_class, self.class_description, w_name, w_desc
        )
        embed = view.build_embed()
        await interaction.followup.send(
            content="⚔️ **Adventure Loadout Preview** — Review your gear before embarking:",
            embed=embed, view=view, ephemeral=True
        )

class LoadoutWeaponSelectView(discord.ui.View):
    def __init__(self, cog: "AdventureCog", user_id: int, session_config: dict, char_class: str, class_description: str):
        super().__init__(timeout=300)
        self.cog = cog
        self.user_id = user_id
        self.session_config = session_config
        self.char_class = char_class
        self.class_description = class_description
        scenario = session_config.get("scenario", "fantasy")
        starting_faction = session_config.get("starting_faction", "public_agency")

        from character_data import get_localized_starting_weapons_map
        user_settings = db.get_settings(self.user_id) if self.user_id else {}
        ui_lang = str((user_settings or {}).get("ui_language") or "en")
        weapons = get_starting_weapons(scenario, starting_faction=starting_faction)
        wpn_labels = get_localized_starting_weapons_map(weapons, ui_lang) if ui_lang != "en" else {}
        options = []
        for w in weapons[:24]:
            try:
                from mechanics.combat.items.weapons import generate_random_equipment as gen_weapon
                from mechanics.combat.items.tags import is_narrative_item
                from scenario_data import is_non_combat_scenario
                w_item = gen_weapon(scenario=scenario, slot="Weapon", tier=3, name=w)
                w_meta = w_item.get("metadata", {})
                arch = w_meta.get("archetype", "Weapon").replace("_", " ").title()
                hand = w_meta.get("handedness", "1H")
                if is_narrative_item(w_meta) or is_non_combat_scenario(scenario):
                    desc = f"{arch} • {hand} • Narrative Item"
                else:
                    mult = w_meta.get("multiplier", 1.0)
                    desc = f"{arch} • {hand} • {mult}x ATK"
            except Exception:
                desc = None
            disp_w = str(wpn_labels.get(w) or w)[:100]
            options.append(discord.SelectOption(label=disp_w, value=w[:100], description=desc[:100] if desc else None))
        options.append(discord.SelectOption(
            label="Custom Weapon...", value="__custom__", description="Name your own custom weapon"
        ))

        select = discord.ui.Select(placeholder=f"Choose a starting weapon ({scenario.title()})...", options=options)
        select.callback = self._on_select
        self.add_item(select)

    async def _on_select(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your adventure setup.", ephemeral=True)
            return
        val = interaction.data["values"][0]
        if val == "__custom__":
            await interaction.response.send_modal(
                LoadoutCustomWeaponModal(self.cog, self.user_id, self.session_config, self.char_class, self.class_description)
            )
        else:
            await interaction.response.defer()
            view = await LoadoutEquipmentPreviewView.create(
                self.cog, self.user_id, self.session_config, self.char_class, self.class_description, val, ""
            )
            embed = view.build_embed()
            await interaction.edit_original_response(
                content="⚔️ **Adventure Loadout Preview** — Review your gear before embarking:",
                embed=embed, view=view
            )

FEMALE_TEXTURE_OPTIONS = [{"value": t, "label": t} for t in FEMALE_ASSET_TEXTURES]

MALE_TEXTURE_OPTIONS = [{"value": t, "label": t} for t in MALE_ASSET_TEXTURES]

MALE_SIZE_OPTIONS = [
    {"value": "small", "label": "Petite / Modest (Compact)"},
    {"value": "average", "label": "Proportional (Average)"},
    {"value": "large", "label": "Well-Endowed / Formidable (Large)"},
    {"value": "huge", "label": "Massive / Heavy (Huge)"},
]

FEMALE_SIZE_OPTIONS = [
    {"value": "flat", "label": "Flat (AA-Cup / Barely There)"},
    {"value": "small", "label": "Petite / Modest (A-B Cup)"},
    {"value": "average", "label": "Proportional (C-Cup)"},
    {"value": "large", "label": "Voluptuous / Full (D-DD Cup)"},
    {"value": "huge", "label": "Bountiful / Massive (E+ Cup)"},
]

REAR_TEXTURE_OPTIONS = [{"value": t, "label": t} for t in REAR_ASSET_TEXTURES]

REAR_SIZE_OPTIONS = [
    {"value": "flat", "label": "Flat (Sleek / Minimal)"},
    {"value": "small", "label": "Compact (Trim / Petite)"},
    {"value": "average", "label": "Shapely (Balanced / Natural)"},
    {"value": "large", "label": "Plump (Curvy / Full)"},
    {"value": "huge", "label": "Bountiful (Wide / Voluptuous)"},
]


class LoadoutEquipmentPreviewView(discord.ui.View):
    def __init__(self, cog: "AdventureCog", user_id: int, session_config: dict,
                 char_class: str, class_description: str, weapon_name: str, weapon_description: str):
        super().__init__(timeout=600)
        self.cog = cog
        self.user_id = user_id
        self.session_config = session_config
        self.char_class = char_class
        self.class_description = class_description
        self.weapon_name = weapon_name
        self.weapon_description = weapon_description
        self._build_components()

    @classmethod
    async def create(cls, cog: "AdventureCog", user_id: int, session_config: dict,
                     char_class: str, class_description: str, weapon_name: str, weapon_description: str):
        view = cls(cog, user_id, session_config, char_class, class_description, weapon_name, weapon_description)
        await view.generate_and_apply_loadout()
        view._build_components()
        return view

    def _is_nsfw(self) -> bool:
        scenario = self.session_config.get("scenario", "fantasy")
        tags = str(self.session_config.get("tags") or "")
        from scenario_data import is_nsfw_scenario
        return is_nsfw_scenario(scenario) or "nsfw" in tags.lower() or (isinstance(scenario, str) and "nsfw" in scenario.lower())

    def _build_components(self):
        self.clear_items()

        # Row 0: Action buttons
        regen_btn = discord.ui.Button(label="Regenerate Equipment", style=discord.ButtonStyle.secondary, emoji="🔄", row=0)
        regen_btn.callback = self._on_regenerate_clicked
        self.add_item(regen_btn)

        is_nsfw = self._is_nsfw()
        char = db.get_character(self.user_id) or {}
        gender = char.get("gender", "Male")
        is_male = is_male_gender(gender)
        feral_rear_excluded = is_feral_rear_excluded(str(char.get("race", "")))

        if is_nsfw:
            roll_btn = discord.ui.Button(label="Roll Feature", style=discord.ButtonStyle.secondary, emoji="🎲", row=0)
            roll_btn.callback = self._on_roll_feature_clicked
            self.add_item(roll_btn)

        begin_btn = discord.ui.Button(label="Begin Adventure", style=discord.ButtonStyle.success, emoji="⚔️", row=0)
        begin_btn.callback = self._on_begin_adventure_clicked
        self.add_item(begin_btn)

        if is_nsfw:
            app = char.get("appearance") or {}
            # Row 1: Size dropdown
            if is_male:
                cur_size = char.get("penis_size") or app.get("penis_size", "average")
                cur_size_tier = classify_asset_size_tier(str(cur_size), "male")
                size_options = []
                for opt in MALE_SIZE_OPTIONS:
                    size_options.append(discord.SelectOption(
                        label=opt["label"][:100],
                        value=opt["value"],
                        default=(opt["value"].lower() == cur_size_tier.lower() or opt["value"].lower() == str(cur_size).lower())
                    ))
                size_select = discord.ui.Select(
                    placeholder="Select Penis Size Tier...",
                    options=size_options,
                    row=1
                )
                size_select.callback = self._on_size_select
                self.add_item(size_select)

                # Row 2: Male Texture dropdown (size-filtered)
                raw_tex = char.get("asset_texture") or app.get("asset_texture", "")
                cur_tex = normalize_asset_texture(str(raw_tex), gender="male", size_tier=cur_size_tier) if raw_tex else ""
                incompat = MALE_TIER_INCOMPATIBLE_TEXTURES.get(cur_size_tier, set())
                allowed_tex = [opt for opt in MALE_TEXTURE_OPTIONS if opt["value"] not in incompat] or MALE_TEXTURE_OPTIONS
                tex_options = [
                    discord.SelectOption(
                        label="Auto-Assign from Race & Build (Dynamic Roll)",
                        value="auto",
                        default=(not cur_tex or cur_tex == "auto")
                    )
                ]
                for opt in allowed_tex[:24]:
                    tex_options.append(discord.SelectOption(
                        label=opt["label"][:100],
                        value=opt["value"],
                        default=(opt["value"] == cur_tex)
                    ))
                tex_select = discord.ui.Select(
                    placeholder="Select Tactile Feature & Texture (Phallus)...",
                    options=tex_options,
                    row=2
                )
                tex_select.callback = self._on_texture_select
                self.add_item(tex_select)
            else:
                cur_size = char.get("breast_size") or app.get("breast_size", "average")
                cur_size_tier = classify_asset_size_tier(str(cur_size), "female")
                size_options = []
                for opt in FEMALE_SIZE_OPTIONS:
                    size_options.append(discord.SelectOption(
                        label=opt["label"][:100],
                        value=opt["value"],
                        default=(opt["value"].lower() == cur_size_tier.lower() or opt["value"].lower() == str(cur_size).lower())
                    ))
                size_select = discord.ui.Select(
                    placeholder="Select Breast Size Tier...",
                    options=size_options,
                    row=1
                )
                size_select.callback = self._on_size_select
                self.add_item(size_select)

                # Row 2: Female Texture dropdown (size-filtered)
                raw_tex = char.get("asset_texture") or app.get("asset_texture", "")
                cur_tex = normalize_asset_texture(str(raw_tex), gender="female", size_tier=cur_size_tier) if raw_tex else ""
                incompat = FEMALE_TIER_INCOMPATIBLE_TEXTURES.get(cur_size_tier, set())
                allowed_tex = [opt for opt in FEMALE_TEXTURE_OPTIONS if opt["value"] not in incompat] or FEMALE_TEXTURE_OPTIONS
                tex_options = [
                    discord.SelectOption(
                        label="Auto-Assign from Race & Build (Dynamic Roll)",
                        value="auto",
                        default=(not cur_tex or cur_tex == "auto")
                    )
                ]
                for opt in allowed_tex[:24]:
                    tex_options.append(discord.SelectOption(
                        label=opt["label"][:100],
                        value=opt["value"],
                        default=(opt["value"] == cur_tex)
                    ))
                tex_select = discord.ui.Select(
                    placeholder="Select Tactile Feature & Texture (Breasts)...",
                    options=tex_options,
                    row=2
                )
                tex_select.callback = self._on_texture_select
                self.add_item(tex_select)

            # Row 3–4: Rear / Ass dropdowns (All Genders, non-feral)
            if not feral_rear_excluded:
                cur_rear_raw = char.get("rear_size") or app.get("rear_size", "average")
                cur_rear_tier = classify_rear_size_tier(str(cur_rear_raw))
                rear_size_options = [
                    discord.SelectOption(
                        label=opt["label"][:100],
                        value=opt["value"],
                        default=(opt["value"].lower() == cur_rear_tier.lower() or opt["value"].lower() == str(cur_rear_raw).lower()),
                    )
                    for opt in REAR_SIZE_OPTIONS
                ]
                rear_size_select = discord.ui.Select(
                    placeholder="Select Rear / Ass Size Tier...",
                    options=rear_size_options,
                    row=3,
                )
                rear_size_select.callback = self._on_rear_size_select
                self.add_item(rear_size_select)

                raw_rtex = char.get("rear_texture") or app.get("rear_texture", "")
                cur_rtex = normalize_rear_texture(str(raw_rtex), size_tier=cur_rear_tier) if raw_rtex else ""
                r_incompat = REAR_TIER_INCOMPATIBLE_TEXTURES.get(cur_rear_tier, set())
                allowed_rtex = [opt for opt in REAR_TEXTURE_OPTIONS if opt["value"] not in r_incompat] or REAR_TEXTURE_OPTIONS
                rtex_options = [
                    discord.SelectOption(
                        label="Auto-Assign from Race & Build (Dynamic Roll)",
                        value="auto",
                        default=(not cur_rtex or cur_rtex == "auto"),
                    )
                ] + [
                    discord.SelectOption(
                        label=opt["label"][:100],
                        value=opt["value"],
                        default=(opt["value"] == cur_rtex),
                    )
                    for opt in allowed_rtex[:24]
                ]
                rtex_select = discord.ui.Select(
                    placeholder="Select Rear Tactile Texture...",
                    options=rtex_options,
                    row=4,
                )
                rtex_select.callback = self._on_rear_texture_select
                self.add_item(rtex_select)

    async def _on_regenerate_clicked(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your setup.", ephemeral=True)
            return
        await interaction.response.defer()
        await self.generate_and_apply_loadout(force_dynamic=True)
        self._build_components()
        embed = self.build_embed()
        await interaction.edit_original_response(embed=embed, view=self)

    async def _on_roll_feature_clicked(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your setup.", ephemeral=True)
            return
        char = await adb(db.get_character, self.user_id)
        if char:
            app = char.get("appearance") or {}
            gender = char.get("gender", "Male")
            is_male = is_male_gender(gender)
            raw_sz = char.get("penis_size") or app.get("penis_size", "average") if is_male else char.get("breast_size") or app.get("breast_size", "average")
            cur_tier = classify_asset_size_tier(str(raw_sz), "male" if is_male else "female")
            chosen = roll_dynamic_asset_texture(
                seed=random.randint(1, 10**9),
                gender="male" if is_male else "female",
                race=char.get("race", "human"),
                physique=str(app.get("physique") or ""),
                size_tier=cur_tier,
            )
            roll_payload = {"asset_texture": chosen}
            if not is_feral_rear_excluded(str(char.get("race", ""))):
                raw_rear = char.get("rear_size") or app.get("rear_size", "average")
                rear_tier = classify_rear_size_tier(str(raw_rear))
                chosen_rear = roll_dynamic_rear_texture(
                    seed=random.randint(1, 10**9),
                    race=char.get("race", "human"),
                    physique=str(app.get("physique") or ""),
                    size_tier=rear_tier,
                )
                roll_payload["rear_texture"] = chosen_rear
            await adb(
                db.update_character_appearance,
                char["id"],
                roll_payload,
            )
            self._char = await adb(db.get_character, self.user_id)
        self._build_components()
        embed = self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    async def _on_size_select(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your setup.", ephemeral=True)
            return
        val = interaction.data["values"][0]
        char = await adb(db.get_character, self.user_id)
        if char:
            gender = char.get("gender", "Male")
            is_male = is_male_gender(gender)
            payload = {"penis_size": val} if is_male else {"breast_size": val}
            await adb(db.update_character_appearance, char["id"], payload)
            self._char = await adb(db.get_character, self.user_id)
        self._build_components()
        embed = self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    async def _on_texture_select(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your setup.", ephemeral=True)
            return
        val = interaction.data["values"][0]
        char = await adb(db.get_character, self.user_id)
        if char:
            payload = {"asset_texture": "" if val == "auto" else val}
            await adb(db.update_character_appearance, char["id"], payload)
            self._char = await adb(db.get_character, self.user_id)
        self._build_components()
        embed = self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    async def _on_rear_size_select(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your setup.", ephemeral=True)
            return
        val = interaction.data["values"][0]
        char = await adb(db.get_character, self.user_id)
        if char:
            app = char.get("appearance") or {}
            payload = {"rear_size": val}
            cur_rtex = char.get("rear_texture") or app.get("rear_texture")
            if cur_rtex:
                healed = heal_rear_texture_for_context(cur_rtex, size_tier=val)
                if healed:
                    payload["rear_texture"] = healed
            await adb(db.update_character_appearance, char["id"], payload)
            self._char = await adb(db.get_character, self.user_id)
        self._build_components()
        embed = self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    async def _on_rear_texture_select(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your setup.", ephemeral=True)
            return
        val = interaction.data["values"][0]
        char = await adb(db.get_character, self.user_id)
        if char:
            payload = {"rear_texture": "" if val == "auto" else val}
            await adb(db.update_character_appearance, char["id"], payload)
            self._char = await adb(db.get_character, self.user_id)
        self._build_components()
        embed = self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    async def _on_begin_adventure_clicked(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your setup.", ephemeral=True)
            return
        await interaction.response.defer()
        for child in self.children:
            child.disabled = True
        await interaction.edit_original_response(content="🎲 Initializing adventure and entering the world...", embed=None, view=None)

        cfg = self.session_config
        capacity = 1 if cfg["mode"] == "solo" else 2
        session_id = await adb(
            db.create_session,
            self.user_id, cfg["mode"], capacity,
            cfg["verbosity"], cfg["dialogue"], cfg["image_gen"],
            cfg["choices_style"], interaction.channel_id,
            scenario=cfg["scenario"],
            result_display=cfg["result_display"],
            combat_ui_style=cfg.get("combat_ui_style", "battle_deck"),
            show_percentages=cfg.get("show_percentages", 1),
            language=cfg.get("language", "en"),
            narration_language=cfg.get("narration_language"),
            character_id=cfg.get("character_id"),
            narrative_pacing=cfg.get("pacing", "balanced"),
            show_enemy_hp=cfg.get("show_enemy_hp", 1),
            show_enemy_intent=cfg.get("show_enemy_intent", 1),
        )
        import scenario_data
        if scenario_data.is_anomalous_incursions_scenario(cfg.get("scenario", "")):
            try:
                from mechanics.world.anomalous_events import bootstrap_anomalous_session
                char_row = (await adb(db.get_character, self.user_id)) or {}
                await adb(
                    bootstrap_anomalous_session,
                    session_id,
                    cfg["scenario"],
                    self.user_id,
                    cfg.get("starting_faction", "public_agency"),
                    char_row.get("name", ""),
                    cfg.get("origin_mode", "") or "",
                    cfg.get("student_grade", "Sophomore") or "Sophomore",
                )
            except Exception:
                pass
        session = await adb(db.get_session, session_id)
        await self.cog.launch_opening_scene(interaction, session, use_followup=True)

    async def generate_and_apply_loadout(self, force_dynamic: bool = False):
        scenario = self.session_config.get("scenario", "fantasy")
        starting_faction = self.session_config.get("starting_faction", "public_agency")
        templates = get_class_templates(scenario, starting_faction=starting_faction)
        is_custom_class = self.char_class not in templates

        char = (await adb(db.get_character, self.user_id)) or {}
        self._char = char
        gender = char.get("gender", "Male")
        race = char.get("race", "Human")

        is_nsfw = self._is_nsfw()

        if is_custom_class:
            from game_engine import turn as _ge_turn
            gear_map = await _ge_turn.generate_custom_starter_gear(
                char_class=self.char_class,
                class_description=self.class_description,
                scenario=scenario,
                gender=gender,
                race=race,
                weapon_name=self.weapon_name
            )
            from scenario_data import is_anomalous_incursions_scenario
            if isinstance(gear_map, dict) and is_anomalous_incursions_scenario(scenario):
                from mechanics.combat.items.anomalous_gear import apply_anomalous_faction_starter_theme
                gear_map = apply_anomalous_faction_starter_theme(
                    gear_map,
                    scenario=scenario,
                    starting_faction=starting_faction,
                    gender=gender,
                    race=race,
                    char_class=self.char_class,
                    starting_weapon=self.weapon_name,
                )
        else:
            from mechanics.combat.items import generate_starter_equipment_loadout
            try:
                gear_map = generate_starter_equipment_loadout(
                    scenario=scenario,
                    char_class=self.char_class,
                    gender=gender,
                    race=race,
                    weapon_name=self.weapon_name,
                    tier=3,
                    is_nsfw=is_nsfw,
                    allow_revealing=bool(force_dynamic and is_nsfw),
                    starting_faction=starting_faction,
                )
            except Exception:
                gear_map = get_starter_gear_by_class(scenario, self.char_class, gender=gender, race=race)

        from scenario_data import is_non_combat_scenario, is_school_scenario
        from mechanics.combat.items.clothing import can_equip_item_in_scenario
        if is_non_combat_scenario(scenario) and isinstance(gear_map, dict):
            gear_map["Weapon"] = None
            gear_map["Shield"] = None
            gear_map["Armor"] = None
            is_school = is_school_scenario(scenario)
            if is_school:
                gear_map["Head"] = None
                gear_map["Gloves"] = None
            else:
                for slot in ("Head", "Gloves"):
                    item = gear_map.get(slot)
                    if item and not can_equip_item_in_scenario(item, slot, scenario)[0]:
                        gear_map[slot] = None

            shoes_item = gear_map.get("Shoes")
            if not shoes_item or not can_equip_item_in_scenario(shoes_item, "Shoes", scenario)[0]:
                gear_map["Shoes"] = (
                    ("Standard School Loafers", "Polished uniform loafers suitable for daily academy wear.", 1)
                    if is_school
                    else ("Comfortable Sneakers", "Flexible and comfortable everyday walking sneakers.", 1)
                )

        starting_items = get_starting_items(scenario, self.char_class, starting_faction=starting_faction)

        await adb(
            db.apply_adventure_loadout,
            user_id=self.user_id,
            scenario=scenario,
            char_class=self.char_class,
            class_description=self.class_description,
            weapon_name=self.weapon_name,
            weapon_description=self.weapon_description,
            gear_map=gear_map,
            starting_items=starting_items,
            attribute=self.session_config.get("attribute"),
            combat_archetype=self.session_config.get("combat_archetype"),
            ability_medium=self.session_config.get("ability_medium"),
        )
        self._equipment = await adb(db.get_equipment, self.user_id)

    def build_embed(self) -> discord.Embed:
        char = getattr(self, "_char", None) or db.get_character(self.user_id)
        equipment = getattr(self, "_equipment", None) or db.get_equipment(self.user_id)
        embed = build_character_sheet_embed(
            char,
            equipment,
            title_prefix="⚔️ Adventure Loadout: ",
            is_nsfw=self._is_nsfw(),
        )
        if self._is_nsfw():
            surf = get_species_surface_profile(
                str((char or {}).get("race", "human")),
                str(((char or {}).get("appearance") or {}).get("skin_type") or ""),
            )
            surf_note = f" | Species Surface: {surf['label']}" if surf.get("label") else ""
            embed.set_footer(text=f"🔞 NSFW Mode Active — Customize intimate anatomy & tactile texture below{surf_note}, then Begin Adventure!")
        else:
            embed.set_footer(text="Click 'Regenerate Equipment' to re-roll starting gear, or 'Begin Adventure' to start!")
        return embed

