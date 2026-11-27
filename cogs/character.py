from __future__ import annotations

import random

import discord
from discord import app_commands
from discord.ext import commands

import db
from db import adb
from character_data import (
    POINT_BUY_POOL,
                             BASE_STAT_VALUE,
                             MAX_STAT_VALUE,
                             STATS,
                             STAT_NAMES,
                             STAT_EMOJI,
                             STAT_EFFECTS,
                             STARTING_GOLD,
                             EQUIPMENT_SLOTS,
                             EQUIPMENT_SLOT_EMOJI,
                             GENDER_OPTIONS,
                             get_item_icon,
)
from scenario_data import load_scenarios


def _is_male_gender(gender: str) -> bool:
    from mechanics.social.persona.core import is_male_gender
    return is_male_gender(gender)


def _is_female_gender(gender: str) -> bool:
    from mechanics.social.persona.core import is_female_gender
    return is_female_gender(gender)


def _allowed_physiques_for(gender: str, stature: str = "", race: str = "") -> list[str]:
    from mechanics.social.persona.core import (
        PHYSIQUE_TIERS,
        STATURE_INCOMPATIBLE_PHYSIQUES,
        GENDER_INCOMPATIBLE_PHYSIQUES,
    )
    from mechanics.social.persona.intimacy.appearance import normalize_stature_tier

    excluded: set[str] = set()
    norm_s = normalize_stature_tier(stature) if stature else ""
    if norm_s:
        excluded.update(STATURE_INCOMPATIBLE_PHYSIQUES.get(norm_s, set()))
    if _is_male_gender(gender):
        excluded.update(GENDER_INCOMPATIBLE_PHYSIQUES.get("male", set()))
    elif _is_female_gender(gender):
        excluded.update(GENDER_INCOMPATIBLE_PHYSIQUES.get("female", set()))
    if "bunian" in str(race or "").strip().lower():
        excluded.update({"Stocky", "Chubby"})
    return [p for p in PHYSIQUE_TIERS if p not in excluded]


_STATURE_RANGE_HINTS: dict[str, str] = {
    "miniature": "(Under 140 cm / <4'7\")",
    "short": "(~145-158 cm / 4'9\"-5'2\")",
    "below_average": "(~158-168 cm / 5'2\"-5'6\")",
    "average": "(~168-178 cm / 5'6\"-5'10\")",
    "tall": "(~178-190 cm / 5'10\"-6'3\")",
    "towering": "(193+ cm / 6'4\"+)",
}


def _format_stature_display(stature: str) -> str:
    if not stature:
        return ""
    from mechanics.social.persona.intimacy.appearance import normalize_stature_tier

    norm = normalize_stature_tier(stature)
    return (norm or str(stature)).replace("_", " ").title()


def _format_stature_option_label(stature: str) -> str:
    label = _format_stature_display(stature)
    hint = _STATURE_RANGE_HINTS.get(str(stature or "").strip().lower(), "")
    return f"{label} {hint}" if (label and hint) else label


def _get_anatomy_option_lists():
    # Lazy import breaks module-top circularity: cogs.adventure.views.loadout imports build_character_sheet_embed.
    from cogs.adventure.views.loadout import (
        FEMALE_SIZE_OPTIONS,
        MALE_SIZE_OPTIONS,
        FEMALE_TEXTURE_OPTIONS,
        MALE_TEXTURE_OPTIONS,
    )
    return FEMALE_SIZE_OPTIONS, MALE_SIZE_OPTIONS, FEMALE_TEXTURE_OPTIONS, MALE_TEXTURE_OPTIONS


def _get_rear_anatomy_option_lists():
    from cogs.adventure.views.loadout import REAR_SIZE_OPTIONS, REAR_TEXTURE_OPTIONS
    return REAR_SIZE_OPTIONS, REAR_TEXTURE_OPTIONS


def build_character_sheet_embed(char: dict, equipment: dict, title_prefix: str = "", *, is_nsfw: bool | None = None) -> discord.Embed:
    from mechanics.social.races import format_race_display
    from mechanics.social.persona.core import heal_physique_for_context
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
    app = char.get("appearance") or {}
    scen_key = char.get("scenario", "fantasy")
    from scenario_data import get_scenario_display_name
    scen_name = get_scenario_display_name(scen_key)
    identity_line = f"Scenario: **{scen_name}**"
    if char.get("race"):
        identity_line += f"  |  Race: **{format_race_display(char['race'])}**"
    if char.get("gender"):
        identity_line += f"  |  Gender: **{char['gender']}**"
    stature_raw = app.get("stature") or app.get("height") or char.get("stature")
    physique_raw = app.get("physique") or char.get("physique")
    build_parts = [
        p for p in (
            _format_stature_display(stature_raw) if stature_raw else "",
            heal_physique_for_context(
                str(physique_raw),
                gender=str(char.get("gender", "")),
                stature=str(stature_raw or "average"),
                race=str(char.get("race", "human")),
            ) if physique_raw else "",
        )
        if p
    ]
    if build_parts:
        identity_line += f"  |  Build: **{' • '.join(build_parts)}**"
    embed.add_field(name="Identity", value=identity_line, inline=False)

    b_size = char.get("breast_size") or app.get("breast_size")
    p_size = char.get("penis_size") or app.get("penis_size")
    a_tex = char.get("asset_texture") or app.get("asset_texture")
    r_size = char.get("rear_size") or app.get("rear_size")
    r_tex = char.get("rear_texture") or app.get("rear_texture")
    from scenario_data import is_nsfw_scenario
    from mechanics.social.persona.intimacy.appearance import (
        is_feral_rear_excluded,
        normalize_asset_texture,
        normalize_rear_size_label,
        normalize_rear_texture,
    )
    show_nsfw = (
        bool(is_nsfw)
        if is_nsfw is not None
        else (is_nsfw_scenario(scen_key) or ("nsfw" in str(char.get("tags") or "").lower()))
    )
    if show_nsfw:
        anat_parts = []
        is_m = _is_male_gender(str(char.get("gender", "")))
        if is_m:
            if p_size:
                anat_parts.append(f"**Size:** {str(p_size).title()}")
        else:
            if b_size:
                anat_parts.append(f"**Size:** {str(b_size).title()}")
        if a_tex:
            norm_a_tex = normalize_asset_texture(str(a_tex), gender="male" if is_m else "female") or str(a_tex)
            anat_parts.append(f"**Tactile/Texture:** {norm_a_tex}")
        if not is_feral_rear_excluded(str(char.get("race", ""))):
            if r_size:
                norm_r_sz = normalize_rear_size_label(str(r_size)) or str(r_size).title()
                anat_parts.append(f"**Rear:** {norm_r_sz}")
            if r_tex:
                norm_r_tex = normalize_rear_texture(str(r_tex)) or str(r_tex)
                anat_parts.append(f"**Rear Texture:** {norm_r_tex}")
        if anat_parts:
            embed.add_field(name="🔞 Intimate Anatomy", value=" • ".join(anat_parts), inline=False)

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
    active_sid = db.get_active_session_id_for_user(char.get("user_id", 0)) if char.get("user_id") else None
    if is_non_combat_scenario(char_scen):
        embed.add_field(
            name="🎭 Scenario Mode",
            value="**Non-Combat (Slice of Life / Drama)**\n*Combat encounters & combat attributes are disabled. Equipment serves as cosmetics & narrative flair.*",
            inline=False
        )
    else:
        from mechanics.social.attributes import calculate_combat_attributes, format_combat_attributes_text
        equipped_list = [item for item in equipment.values() if item] if equipment else None
        attrs = calculate_combat_attributes(char, equipped_list, scenario=char_scen, session_id=active_sid)
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
        known_sids = list(db.get_learned_spells(char.get("user_id", 0), char=char) or [])
        if active_sid:
            try:
                from mechanics.combat.spells.spirit_court_perks import get_active_spirit_court_summon_spell_ids
                for _sc_sid in get_active_spirit_court_summon_spell_ids(int(active_sid)):
                    if _sc_sid not in known_sids:
                        known_sids.append(_sc_sid)
            except Exception:
                pass
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
        self.selected_stature: str = ""
        self.selected_physique: str = ""
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

        from mechanics.social.persona.core import STATURE_TIERS

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

        stature_options = [
            discord.SelectOption(
                label="Height: Auto-Roll (Race-Aware)",
                value="__auto__",
                default=(not self.selected_stature),
            )
        ] + [
            discord.SelectOption(
                label=_format_stature_option_label(tier),
                value=tier,
                default=(tier == self.selected_stature),
            )
            for tier in STATURE_TIERS
        ]
        stature_select = discord.ui.Select(
            placeholder="Height (optional — default Auto-Roll)",
            options=stature_options,
            row=3,
        )
        stature_select.callback = self._on_stature_select
        self.add_item(stature_select)

        allowed_physiques = _allowed_physiques_for(self.gender, self.selected_stature, race=self.race)
        physique_options = [
            discord.SelectOption(
                label="Physique: Auto-Roll",
                value="__auto__",
                default=(not self.selected_physique),
            )
        ] + [
            discord.SelectOption(
                label=p,
                value=p,
                default=(p == self.selected_physique),
            )
            for p in allowed_physiques
        ]
        physique_select = discord.ui.Select(
            placeholder="Physique (optional — default Auto-Roll)",
            options=physique_options,
            row=4,
        )
        physique_select.callback = self._on_physique_select
        self.add_item(physique_select)

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
        stature_label = _format_stature_display(self.selected_stature) if self.selected_stature else "Auto-Roll"
        physique_label = self.selected_physique if self.selected_physique else "Auto-Roll"
        embed.add_field(
            name="Identity",
            value=f"Race: {race_str}\nGender: {self.gender}\nBuild: {stature_label} • {physique_label}",
            inline=True,
        )
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

    async def _on_stature_select(self, interaction: discord.Interaction):
        if not await self._guard(interaction):
            return
        val = interaction.data["values"][0]
        self.selected_stature = "" if val == "__auto__" else val
        if self.selected_physique:
            from mechanics.social.persona.core import heal_physique_for_context

            self.selected_physique = heal_physique_for_context(
                self.selected_physique,
                gender=self.gender,
                stature=self.selected_stature or "average",
                race=self.race,
            )
        self._rebuild()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def _on_physique_select(self, interaction: discord.Interaction):
        if not await self._guard(interaction):
            return
        val = interaction.data["values"][0]
        self.selected_physique = "" if val == "__auto__" else val
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

        leftover = self.points_remaining
        appearance_payload = {}
        if self.selected_stature:
            appearance_payload["stature"] = self.selected_stature
        if self.selected_physique:
            appearance_payload["physique"] = self.selected_physique
        char = await adb(db.create_character,
            self.user_id, self.name, char_class="Adventurer", class_description="",
            stats=self.values, gold=STARTING_GOLD, pending_stat_points=leftover,
            gender=self.gender, scenario=self.scenario,
            race=self.race, race_description=self.race_description,
            appearance=appearance_payload or None,
        )
        equipment = await adb(db.get_equipment, self.user_id)

        embed = build_character_sheet_embed(char, equipment, title_prefix="✨ Character Created: ")
        embed.set_footer(text="Use /adventure start to embark on a quest and pick your scenario loadout.")

        await interaction.response.edit_message(content=None, embed=embed, view=None)
        self.stop()

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True


class CharacterAppearanceEditView(discord.ui.View):
    """Ephemeral editor for height, physique, and (when NSFW-gated) intimate anatomy."""

    def __init__(self, owner_id: int, char: dict, allow_nsfw: bool = False):
        super().__init__(timeout=300)
        self.owner_id = owner_id
        self.char = char
        self.allow_nsfw = bool(allow_nsfw)
        self._edit_tab = "primary"
        self._rebuild()

    def _current_state(self) -> tuple[str, str, bool]:
        from mechanics.social.persona.core import heal_physique_for_context
        from mechanics.social.persona.intimacy.appearance import normalize_stature_tier

        app = self.char.get("appearance") or {}
        stature_raw = app.get("stature") or app.get("height") or self.char.get("stature") or "average"
        physique_raw = app.get("physique") or self.char.get("physique") or "Average"
        cur_stature = normalize_stature_tier(str(stature_raw)) or "average"
        cur_physique = heal_physique_for_context(
            str(physique_raw),
            gender=self.char.get("gender", ""),
            stature=cur_stature,
            race=self.char.get("race", "human"),
        ) or "Average"
        is_male = _is_male_gender(self.char.get("gender", ""))
        return cur_stature, cur_physique, is_male

    def _rebuild(self):
        self.clear_items()
        from mechanics.social.persona.core import STATURE_TIERS
        from mechanics.social.persona.intimacy.appearance import is_feral_rear_excluded

        cur_stature, cur_physique, is_male = self._current_state()
        feral_rear_excluded = is_feral_rear_excluded(str(self.char.get("race", "")))
        if feral_rear_excluded and self._edit_tab == "rear":
            self._edit_tab = "primary"
        allowed_physiques = _allowed_physiques_for(
            self.char.get("gender", ""),
            cur_stature,
            race=str(self.char.get("race", "")),
        )

        stature_options = [
            discord.SelectOption(
                label=_format_stature_option_label(tier),
                value=tier,
                default=(tier == cur_stature),
            )
            for tier in STATURE_TIERS
        ]
        stature_select = discord.ui.Select(placeholder="Select Height...", options=stature_options, row=0)
        stature_select.callback = self._on_stature_select
        self.add_item(stature_select)

        physique_options = [
            discord.SelectOption(
                label=p,
                value=p,
                default=(p == cur_physique),
            )
            for p in allowed_physiques
        ]
        physique_select = discord.ui.Select(placeholder="Select Physique...", options=physique_options, row=1)
        physique_select.callback = self._on_physique_select
        self.add_item(physique_select)

        roll_build_btn = discord.ui.Button(
            label="Roll Build",
            emoji="🎲",
            style=discord.ButtonStyle.secondary,
            row=2,
        )
        roll_build_btn.callback = self._on_roll_build
        self.add_item(roll_build_btn)

        if self.allow_nsfw:
            roll_feature_btn = discord.ui.Button(
                label="Roll Rear Feature" if (self._edit_tab == "rear" and not feral_rear_excluded) else "Roll Feature",
                emoji="✨",
                style=discord.ButtonStyle.secondary,
                row=2,
            )
            roll_feature_btn.callback = self._on_roll_feature
            self.add_item(roll_feature_btn)

            if not feral_rear_excluded:
                toggle_tab_btn = discord.ui.Button(
                    label=("Edit Phallus" if is_male else "Edit Breasts") if self._edit_tab == "rear" else "Edit Rear / Ass",
                    emoji="🔞" if self._edit_tab == "rear" else "🍑",
                    style=discord.ButtonStyle.primary if self._edit_tab == "rear" else discord.ButtonStyle.secondary,
                    row=2,
                )
                toggle_tab_btn.callback = self._on_toggle_anatomy_tab
                self.add_item(toggle_tab_btn)

            app = self.char.get("appearance") or {}
            if self._edit_tab == "rear" and not feral_rear_excluded:
                from mechanics.social.persona.intimacy.constants import REAR_TIER_INCOMPATIBLE_TEXTURES
                from mechanics.social.persona.intimacy.appearance import (
                    classify_rear_size_tier,
                    normalize_rear_texture,
                )

                REAR_SIZE_OPTIONS, REAR_TEXTURE_OPTIONS = _get_rear_anatomy_option_lists()
                cur_rear_raw = self.char.get("rear_size") or app.get("rear_size", "average")
                cur_rear_tier = classify_rear_size_tier(str(cur_rear_raw))
                rear_size_opts = [
                    discord.SelectOption(
                        label=opt["label"][:100],
                        value=opt["value"],
                        default=(opt["value"].lower() == cur_rear_tier.lower() or opt["value"].lower() == str(cur_rear_raw).lower()),
                    )
                    for opt in REAR_SIZE_OPTIONS
                ]
                rear_size_select = discord.ui.Select(
                    placeholder="Select Rear / Ass Size Tier...",
                    options=rear_size_opts,
                    row=3,
                )
                rear_size_select.callback = self._on_rear_size_select
                self.add_item(rear_size_select)

                raw_rtex = self.char.get("rear_texture") or app.get("rear_texture", "")
                cur_rtex = normalize_rear_texture(str(raw_rtex), size_tier=cur_rear_tier) if raw_rtex else ""
                r_incompat = REAR_TIER_INCOMPATIBLE_TEXTURES.get(cur_rear_tier, set())
                r_tex_pool = [opt for opt in REAR_TEXTURE_OPTIONS if opt["value"] not in r_incompat] or REAR_TEXTURE_OPTIONS
                r_tex_options = [
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
                    for opt in r_tex_pool[:24]
                ]
                r_tex_select = discord.ui.Select(
                    placeholder="Select Rear Tactile Texture...",
                    options=r_tex_options,
                    row=4,
                )
                r_tex_select.callback = self._on_rear_texture_select
                self.add_item(r_tex_select)
            else:
                from mechanics.social.persona.intimacy.constants import (
                    FEMALE_TIER_INCOMPATIBLE_TEXTURES,
                    MALE_TIER_INCOMPATIBLE_TEXTURES,
                )
                from mechanics.social.persona.intimacy.appearance import (
                    classify_asset_size_tier,
                    normalize_asset_texture,
                )

                FEMALE_SIZE_OPTIONS, MALE_SIZE_OPTIONS, FEMALE_TEXTURE_OPTIONS, MALE_TEXTURE_OPTIONS = _get_anatomy_option_lists()
                if is_male:
                    cur_size_raw = self.char.get("penis_size") or app.get("penis_size", "average")
                    cur_size_tier = classify_asset_size_tier(str(cur_size_raw), "male")
                    size_opts = [
                        discord.SelectOption(
                            label=opt["label"][:100],
                            value=opt["value"],
                            default=(opt["value"].lower() == cur_size_tier.lower() or opt["value"].lower() == str(cur_size_raw).lower()),
                        )
                        for opt in MALE_SIZE_OPTIONS
                    ]
                    size_placeholder = "Select Penis Size Tier..."
                    incompat = MALE_TIER_INCOMPATIBLE_TEXTURES.get(cur_size_tier, set())
                    tex_pool = [opt for opt in MALE_TEXTURE_OPTIONS if opt["value"] not in incompat] or MALE_TEXTURE_OPTIONS
                    tex_placeholder = "Select Tactile Feature & Texture (Phallus)..."
                else:
                    cur_size_raw = self.char.get("breast_size") or app.get("breast_size", "average")
                    cur_size_tier = classify_asset_size_tier(str(cur_size_raw), "female")
                    size_opts = [
                        discord.SelectOption(
                            label=opt["label"][:100],
                            value=opt["value"],
                            default=(opt["value"].lower() == cur_size_tier.lower() or opt["value"].lower() == str(cur_size_raw).lower()),
                        )
                        for opt in FEMALE_SIZE_OPTIONS
                    ]
                    size_placeholder = "Select Breast Size Tier..."
                    incompat = FEMALE_TIER_INCOMPATIBLE_TEXTURES.get(cur_size_tier, set())
                    tex_pool = [opt for opt in FEMALE_TEXTURE_OPTIONS if opt["value"] not in incompat] or FEMALE_TEXTURE_OPTIONS
                    tex_placeholder = "Select Tactile Feature & Texture (Breasts)..."

                size_select = discord.ui.Select(placeholder=size_placeholder, options=size_opts, row=3)
                size_select.callback = self._on_size_select
                self.add_item(size_select)

                raw_tex = self.char.get("asset_texture") or app.get("asset_texture", "")
                cur_tex = normalize_asset_texture(str(raw_tex), gender="male" if is_male else "female", size_tier=cur_size_tier) if raw_tex else ""
                tex_options = [
                    discord.SelectOption(
                        label="Auto-Assign from Race & Build (Dynamic Roll)",
                        value="auto",
                        default=(not cur_tex or cur_tex == "auto"),
                    )
                ] + [
                    discord.SelectOption(
                        label=opt["label"][:100],
                        value=opt["value"],
                        default=(opt["value"] == cur_tex),
                    )
                    for opt in tex_pool[:24]
                ]
                tex_select = discord.ui.Select(placeholder=tex_placeholder, options=tex_options, row=4)
                tex_select.callback = self._on_texture_select
                self.add_item(tex_select)

    def build_embed(self) -> discord.Embed:
        from mechanics.social.races import format_race_display
        from mechanics.social.persona.intimacy.appearance import (
            classify_rear_size_tier,
            get_species_surface_profile,
            is_feral_rear_excluded,
            normalize_asset_texture,
            normalize_rear_size_label,
            normalize_rear_texture,
        )

        cur_stature, cur_physique, is_male = self._current_state()
        app = self.char.get("appearance") or {}
        embed = discord.Embed(
            title=f"📐 Customize Appearance — {self.char.get('name', 'Character')}",
            description="Adjust your character's physical build and appearance.",
            color=discord.Color.gold(),
        )
        race_str = format_race_display(self.char.get("race", "human"))
        gender_str = self.char.get("gender", "Unknown")
        embed.add_field(
            name="Identity",
            value=f"Race: **{race_str}**  |  Gender: **{gender_str}**",
            inline=False,
        )
        embed.add_field(
            name="Physical Build",
            value=f"Height: **{_format_stature_display(cur_stature)}**\nPhysique: **{cur_physique}**",
            inline=False,
        )
        if self.allow_nsfw:
            feral_rear_excluded = is_feral_rear_excluded(str(self.char.get("race", "")))
            size_label = (
                self.char.get("penis_size") or app.get("penis_size") or "Average"
                if is_male
                else self.char.get("breast_size") or app.get("breast_size") or "Modest B-Cup"
            )
            raw_tex = self.char.get("asset_texture") or app.get("asset_texture") or ""
            tex_label = (
                normalize_asset_texture(str(raw_tex), gender="male" if is_male else "female") or raw_tex or "Auto-Assigned"
            )
            tab_label = (
                "🍑 Rear / Ass"
                if (self._edit_tab == "rear" and not feral_rear_excluded)
                else ("🔞 Phallus" if is_male else "🔞 Breasts")
            )
            surf = get_species_surface_profile(self.char.get("race", "human"), str(app.get("skin_type") or ""))
            anat_lines = [
                f"Active Tab: **{tab_label}**",
                f"Size: **{size_label}**",
                f"Tactile Texture: **{tex_label}**",
            ]
            if not feral_rear_excluded:
                r_size_raw = self.char.get("rear_size") or app.get("rear_size") or "average"
                r_size_label = normalize_rear_size_label(str(r_size_raw)) or str(r_size_raw).title()
                raw_rtex = self.char.get("rear_texture") or app.get("rear_texture") or ""
                r_tex_label = (
                    normalize_rear_texture(str(raw_rtex), size_tier=classify_rear_size_tier(str(r_size_raw)))
                    or raw_rtex
                    or "Auto-Assigned"
                )
                anat_lines.append(f"Rear: **{r_size_label}**")
                anat_lines.append(f"Rear Texture: **{r_tex_label}**")
            if surf.get("label"):
                anat_lines.append(f"Species Surface: **{surf['label']}** *(auto from race)*")
            anat_val = "\n".join(anat_lines)
            embed.add_field(
                name="🔞 Intimate Anatomy",
                value=anat_val,
                inline=False,
            )
        return embed

    async def _guard(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Only the character owner can edit this appearance.", ephemeral=True)
            return False
        return True

    async def _apply_update(self, interaction: discord.Interaction, payload: dict):
        updated = await adb(db.update_character_appearance, self.char["id"], payload)
        if updated:
            self.char = updated
        self._rebuild()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def _on_stature_select(self, interaction: discord.Interaction):
        if not await self._guard(interaction):
            return
        from mechanics.social.persona.core import heal_physique_for_context

        new_stature = interaction.data["values"][0]
        _, cur_physique, _ = self._current_state()
        healed = heal_physique_for_context(
            cur_physique,
            gender=self.char.get("gender", ""),
            stature=new_stature,
            race=self.char.get("race", "human"),
        )
        await self._apply_update(interaction, {"stature": new_stature, "physique": healed})

    async def _on_physique_select(self, interaction: discord.Interaction):
        if not await self._guard(interaction):
            return
        new_physique = interaction.data["values"][0]
        await self._apply_update(interaction, {"physique": new_physique})

    async def _on_roll_build(self, interaction: discord.Interaction):
        if not await self._guard(interaction):
            return
        from mechanics.social.persona.intimacy.appearance import roll_dynamic_stature, roll_dynamic_physique

        race = self.char.get("race", "human")
        gender = self.char.get("gender", "female")
        new_stature = roll_dynamic_stature(race=race, gender=gender, seed=None)
        new_physique = roll_dynamic_physique(gender=gender, stature=new_stature, race=race, seed=None)
        await self._apply_update(interaction, {"stature": new_stature, "physique": new_physique})

    async def _on_toggle_anatomy_tab(self, interaction: discord.Interaction):
        if not await self._guard(interaction):
            return
        self._edit_tab = "primary" if self._edit_tab == "rear" else "rear"
        self._rebuild()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def _on_roll_feature(self, interaction: discord.Interaction):
        if not await self._guard(interaction):
            return
        from mechanics.social.persona.intimacy.appearance import (
            classify_asset_size_tier,
            classify_rear_size_tier,
            roll_dynamic_asset_texture,
            roll_dynamic_rear_texture,
        )

        _, cur_physique, is_male = self._current_state()
        app = self.char.get("appearance") or {}
        if self._edit_tab == "rear":
            raw_rear = self.char.get("rear_size") or app.get("rear_size", "average")
            rear_tier = classify_rear_size_tier(str(raw_rear))
            chosen = roll_dynamic_rear_texture(
                seed=random.randint(1, 10**9),
                race=self.char.get("race", "human"),
                physique=cur_physique,
                size_tier=rear_tier,
            )
            await self._apply_update(interaction, {"rear_texture": chosen})
            return

        eff_g = "male" if is_male else "female"
        raw_sz = self.char.get("penis_size") or app.get("penis_size", "average") if is_male else self.char.get("breast_size") or app.get("breast_size", "average")
        cur_tier = classify_asset_size_tier(str(raw_sz), eff_g)
        chosen = roll_dynamic_asset_texture(
            seed=random.randint(1, 10**9),
            gender=eff_g,
            race=self.char.get("race", "human"),
            physique=cur_physique,
            size_tier=cur_tier,
        )
        await self._apply_update(interaction, {"asset_texture": chosen})

    async def _on_size_select(self, interaction: discord.Interaction):
        if not await self._guard(interaction):
            return
        from mechanics.social.persona.intimacy.appearance import heal_asset_texture_for_context

        _, _, is_male = self._current_state()
        app = self.char.get("appearance") or {}
        val = interaction.data["values"][0]
        eff_g = "male" if is_male else "female"
        payload = {"penis_size": val} if is_male else {"breast_size": val}
        cur_tex = self.char.get("asset_texture") or app.get("asset_texture")
        if cur_tex:
            healed_tex = heal_asset_texture_for_context(cur_tex, gender=eff_g, size_tier=val)
            if healed_tex:
                payload["asset_texture"] = healed_tex
        await self._apply_update(interaction, payload)

    async def _on_texture_select(self, interaction: discord.Interaction):
        if not await self._guard(interaction):
            return
        val = interaction.data["values"][0]
        payload = {"asset_texture": "" if val == "auto" else val}
        await self._apply_update(interaction, payload)

    async def _on_rear_size_select(self, interaction: discord.Interaction):
        if not await self._guard(interaction):
            return
        from mechanics.social.persona.intimacy.appearance import heal_rear_texture_for_context

        app = self.char.get("appearance") or {}
        val = interaction.data["values"][0]
        payload = {"rear_size": val}
        cur_rtex = self.char.get("rear_texture") or app.get("rear_texture")
        if cur_rtex:
            healed = heal_rear_texture_for_context(cur_rtex, size_tier=val)
            if healed:
                payload["rear_texture"] = healed
        await self._apply_update(interaction, payload)

    async def _on_rear_texture_select(self, interaction: discord.Interaction):
        if not await self._guard(interaction):
            return
        val = interaction.data["values"][0]
        payload = {"rear_texture": "" if val == "auto" else val}
        await self._apply_update(interaction, payload)

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True


class CharacterSheetView(discord.ui.View):
    """Attached to `/character sheet` with an owner-locked ephemeral Edit Appearance button."""

    def __init__(self, owner_id: int):
        super().__init__(timeout=300)
        self.owner_id = owner_id

    @discord.ui.button(label="Edit Appearance", emoji="📐", style=discord.ButtonStyle.secondary)
    async def edit_appearance(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Only the character owner can edit appearance.", ephemeral=True)
            return
        char = await adb(db.get_character, self.owner_id)
        if not char:
            await interaction.response.send_message(
                "No active character found. Use `/character create` first.",
                ephemeral=True,
            )
            return
        from scenario_data import is_nsfw_scenario
        from cogs.scenario_picker import channel_allows_nsfw

        allow_nsfw = is_nsfw_scenario(char.get("scenario", "fantasy")) and channel_allows_nsfw(interaction.channel)
        view = CharacterAppearanceEditView(self.owner_id, char, allow_nsfw=allow_nsfw)
        await interaction.response.send_message(embed=view.build_embed(), view=view, ephemeral=True)

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

        import scenario_variants
        scenarios = load_scenarios()
        # Only family roots here; variants are offered in a follow-up picker.
        options = []
        for key in scenario_variants.get_family_root_keys()[:25]:
            entry = scenarios[key]
            count = len(scenario_variants.get_family_variants(key))
            label = entry["name"] + (f" ({count} variants)" if count > 1 else "")
            options.append(discord.SelectOption(label=label[:100], value=key,
                                                description=entry["description"][:100]))
        select = discord.ui.Select(placeholder="Choose a scenario...", options=options)
        select.callback = self._on_select
        self.add_item(select)

    async def _on_select(self, interaction: discord.Interaction):
        from cogs.scenario_picker import (
            ScenarioVariantSelectView, channel_allows_nsfw, hidden_nsfw_note, needs_variant_step,
        )
        scenario_key = interaction.data["values"][0]
        allow_nsfw = channel_allows_nsfw(interaction.channel)
        if needs_variant_step(scenario_key, allow_nsfw):
            family_name = load_scenarios().get(scenario_key, {}).get("name", scenario_key)
            view = ScenarioVariantSelectView(interaction.user.id, scenario_key, self._go_to_gender,
                                             allow_nsfw=allow_nsfw)
            await interaction.response.edit_message(
                content=(f"Scenario: **{family_name}**. Choose a variant:"
                         f"{hidden_nsfw_note(scenario_key, allow_nsfw)}"),
                view=view)
            return
        await self._go_to_gender(interaction, scenario_key)

    async def _go_to_gender(self, interaction: discord.Interaction, scenario_key: str):
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

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user:
            try:
                await adb(db.save_discord_user, interaction.user.id, interaction.user.name, interaction.user.display_name)
            except Exception:
                pass
        return True

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

            from mechanics.social.races import format_race_display
            race_display = format_race_display(char.get("race", "human"))
            gender_display = char.get("gender", "Unknown")

            value = (
                f"**Race & Gender:** {race_display} | {gender_display}\n"
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

        from mechanics.social.races import format_race_display
        race_display = format_race_display(switched.get("race", "human"))
        gender_display = switched.get("gender", "Unknown")

        embed = discord.Embed(
            title=f"🔄 Switched Active Character to {switched['name']}",
            description=f"**Race & Gender:** {race_display} | {gender_display}\n"
                        f"**Class:** {switched['char_class']} (Level {switched['level']})\n"
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
            from mechanics.social.races import format_race_display
            race_display = format_race_display(c.get("race", "human"))
            gender_str = f" {c.get('gender')}" if c.get("gender") else ""
            label = f"{c['name']} - {race_display}{gender_str} Lvl {c['level']} {c['char_class']}{active_str}"
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
        await interaction.response.send_message(embed=embed, view=CharacterSheetView(interaction.user.id))

    @character_group.command(name="appearance", description="Customize your character's height, physique, and appearance")
    async def appearance(self, interaction: discord.Interaction):
        char = await adb(db.get_character, interaction.user.id)
        if not char:
            await interaction.response.send_message(
                "You don't have a character yet. Use `/character create` first.", ephemeral=True)
            return
        from scenario_data import is_nsfw_scenario
        from cogs.scenario_picker import channel_allows_nsfw

        allow_nsfw = is_nsfw_scenario(char.get("scenario", "fantasy")) and channel_allows_nsfw(interaction.channel)
        view = CharacterAppearanceEditView(interaction.user.id, char, allow_nsfw=allow_nsfw)
        await interaction.response.send_message(embed=view.build_embed(), view=view, ephemeral=True)

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
