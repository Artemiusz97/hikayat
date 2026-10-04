"""
Discord Cog for viewing and managing NPC contacts & relationship meters.
"""
import discord
from discord import app_commands
from discord.ext import commands

import db
from db import adb
import scenario_data
from mechanics.social.relationships import (
    get_relationship_tier,
    get_relationship_modifier,
    format_progress_bar,
    get_unlocked_info_level
)
from mechanics.social.races import format_race_display

def get_scenario_contact_title(scen_key: str) -> tuple[str, str]:
    from scenario_data import has_tag
    if has_tag(scen_key, "high_school") or has_tag(scen_key, "high_school_drama"): return ("📱", "Student Directory & Phone Contacts")
    if has_tag(scen_key, "space") or has_tag(scen_key, "sci_fi"): return ("🚀", "Starship Log & Planetary Contacts")
    if has_tag(scen_key, "cyberpunk"): return ("💾", "Neural Cyberdeck Contacts & Agent Dossier")
    if has_tag(scen_key, "steampunk"): return ("⚙️", "Brass Telegraph Registry & Contact Ledger")
    if has_tag(scen_key, "grimdark") or has_tag(scen_key, "dark_fantasy"): return ("📜", "Gothic Codex of Acquaintances")
    if has_tag(scen_key, "post_apocalypse") or has_tag(scen_key, "nuclear_post_apocalypse"): return ("📻", "Wasteland Radio Contacts & Survivors")
    if has_tag(scen_key, "isekai") or has_tag(scen_key, "isekai_fantasy"): return ("✨", "Companion & Relationship Codex")
    return ("📜", "Codex of Acquaintances")


class ContactSelect(discord.ui.Select):
    def __init__(self, page_contacts: list[dict], all_contacts: list[dict], scenario_key: str, page: int = 0, total_pages: int = 1,
                 session_id: int = 0, cog = None, from_phone: bool = False):
        options = []
        for c in page_contacts:
            name = c.get("name", "Unknown NPC")
            score = c.get("relationship_score", 0)
            track = c.get("track", "platonic")
            tier = get_relationship_tier(score, track, scenario_key)
            role = c.get("basic_info", {}).get("role") or c.get("basic_info", {}).get("occupation") or "NPC"
            grade = c.get("basic_info", {}).get("grade") or ""
            grade_prefix = f"[{grade}] " if grade else ""

            label = f"{name} ({tier['name']})"
            description = f"{grade_prefix}{role} | Score: {score}"
            val = str(c.get("npc_id") or name or "npc")[:100]
            options.append(
                discord.SelectOption(
                    label=label[:100],
                    description=description[:100],
                    value=val
                )
            )

        placeholder = f"Select a contact (Page {page + 1}/{total_pages})..." if total_pages > 1 else "Select a contact to view details..."
        super().__init__(placeholder=placeholder, min_values=1, max_values=1, options=options, row=0)
        self.contacts_dict = {c["npc_id"]: c for c in all_contacts}
        self.all_contacts = all_contacts
        self.scenario_key = scenario_key
        self.page = page
        self.session_id = session_id
        self.cog = cog
        self.from_phone = from_phone

    async def callback(self, interaction: discord.Interaction):
        npc_id = self.values[0]
        contact = self.contacts_dict.get(npc_id)
        if not contact:
            await interaction.response.send_message("Contact not found.", ephemeral=True)
            return

        embed = build_contact_detail_embed(contact, self.scenario_key, user_id=interaction.user.id)
        new_view = ContactView(
            self.all_contacts, self.scenario_key, interaction.user.id,
            active_contact=contact, page=self.page,
            session_id=self.session_id, cog=self.cog, from_phone=self.from_phone
        )
        await interaction.response.edit_message(embed=embed, view=new_view)


class RomanticMemoriesButton(discord.ui.Button):
    def __init__(self, contact: dict, scenario_key: str, user_id: int, contacts: list[dict],
                 session_id: int = 0, cog = None, from_phone: bool = False):
        super().__init__(label="Romantic Memories", emoji="📖", style=discord.ButtonStyle.secondary, row=1)
        self.contact = contact
        self.scenario_key = scenario_key
        self.user_id = user_id
        self.contacts = contacts
        self.session_id = session_id
        self.cog = cog
        self.from_phone = from_phone

    async def callback(self, interaction: discord.Interaction):
        embed = build_romantic_memories_embed(self.contact, scenario_key=self.scenario_key, user_id=self.user_id)
        view = RomanticMemoriesView(
            self.contact, self.scenario_key, self.user_id, self.contacts,
            session_id=self.session_id, cog=self.cog, from_phone=self.from_phone
        )
        await interaction.response.edit_message(embed=embed, view=view)


class RelationsButton(discord.ui.Button):
    def __init__(self, contact: dict, scenario_key: str, user_id: int, contacts: list[dict],
                 session_id: int = 0, cog = None, from_phone: bool = False):
        super().__init__(label="Relations & Family", emoji="👑", style=discord.ButtonStyle.secondary, row=1)
        self.contact = contact
        self.scenario_key = scenario_key
        self.user_id = user_id
        self.contacts = contacts
        self.session_id = session_id
        self.cog = cog
        self.from_phone = from_phone

    async def callback(self, interaction: discord.Interaction):
        embed = build_relations_embed(self.contact, scenario_key=self.scenario_key, user_id=self.user_id)
        view = RelationsView(
            self.contact, self.scenario_key, self.user_id, self.contacts,
            session_id=self.session_id, cog=self.cog, from_phone=self.from_phone
        )
        await interaction.response.edit_message(embed=embed, view=view)


class IntimateProfileButton(discord.ui.Button):
    def __init__(self, contact: dict, scenario_key: str, user_id: int, contacts: list[dict],
                 session_id: int = 0, cog = None, from_phone: bool = False):
        super().__init__(label="Intimate Profile", emoji="🔞", style=discord.ButtonStyle.secondary, row=1)
        self.contact = contact
        self.scenario_key = scenario_key
        self.user_id = user_id
        self.contacts = contacts
        self.session_id = session_id
        self.cog = cog
        self.from_phone = from_phone

    async def callback(self, interaction: discord.Interaction):
        embed = build_intimate_profile_embed(self.contact, scenario_key=self.scenario_key, user_id=self.user_id)
        view = IntimateProfileView(
            self.contact, self.scenario_key, self.user_id, self.contacts,
            session_id=self.session_id, cog=self.cog, from_phone=self.from_phone
        )
        await interaction.response.edit_message(embed=embed, view=view)


class IntimateProfileView(discord.ui.View):
    def __init__(self, contact: dict, scenario_key: str, user_id: int, contacts: list[dict],
                 session_id: int = 0, cog = None, from_phone: bool = False):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.add_item(BackToProfileButton(
            contact, scenario_key, user_id, contacts,
            session_id=session_id, cog=cog, from_phone=from_phone
        ))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This contact view is for another player.", ephemeral=True)
            return False
        return True


class BackToProfileButton(discord.ui.Button):
    def __init__(self, contact: dict, scenario_key: str, user_id: int, contacts: list[dict],
                 session_id: int = 0, cog = None, from_phone: bool = False):
        super().__init__(label="Back to Profile", emoji="🔙", style=discord.ButtonStyle.primary)
        self.contact = contact
        self.scenario_key = scenario_key
        self.user_id = user_id
        self.contacts = contacts
        self.session_id = session_id
        self.cog = cog
        self.from_phone = from_phone

    async def callback(self, interaction: discord.Interaction):
        embed = build_contact_detail_embed(self.contact, self.scenario_key, user_id=self.user_id)
        view = ContactView(
            self.contacts, self.scenario_key, self.user_id,
            active_contact=self.contact,
            session_id=self.session_id, cog=self.cog, from_phone=self.from_phone
        )
        await interaction.response.edit_message(embed=embed, view=view)


class RomanticMemoriesView(discord.ui.View):
    def __init__(self, contact: dict, scenario_key: str, user_id: int, contacts: list[dict],
                 session_id: int = 0, cog = None, from_phone: bool = False):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.add_item(BackToProfileButton(
            contact, scenario_key, user_id, contacts,
            session_id=session_id, cog=cog, from_phone=from_phone
        ))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This contact view is for another player.", ephemeral=True)
            return False
        return True


class RelationsView(discord.ui.View):
    def __init__(self, contact: dict, scenario_key: str, user_id: int, contacts: list[dict],
                 session_id: int = 0, cog = None, from_phone: bool = False):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.add_item(BackToProfileButton(
            contact, scenario_key, user_id, contacts,
            session_id=session_id, cog=cog, from_phone=from_phone
        ))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This contact view is for another player.", ephemeral=True)
            return False
        return True


class ContactView(discord.ui.View):
    def __init__(self, contacts: list[dict], scenario_key: str, user_id: int,
                 active_contact: dict = None, page: int = 0,
                 session_id: int = 0, cog = None, from_phone: bool = False):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.contacts = contacts
        self.scenario_key = scenario_key
        self.active_contact = active_contact
        self.page = page
        self.session_id = session_id
        self.cog = cog
        self.from_phone = from_phone
        self.page_size = 25
        self.total_pages = max(1, (len(contacts) + self.page_size - 1) // self.page_size)

        start = self.page * self.page_size
        end = start + self.page_size
        page_contacts = contacts[start:end]

        if contacts:
            self.add_item(ContactSelect(
                page_contacts, contacts, scenario_key, page=self.page, total_pages=self.total_pages,
                session_id=session_id, cog=cog, from_phone=from_phone
            ))
        if active_contact:
            self.add_item(RelationsButton(
                active_contact, scenario_key, user_id, contacts,
                session_id=session_id, cog=cog, from_phone=from_phone
            ))
            self.add_item(RomanticMemoriesButton(
                active_contact, scenario_key, user_id, contacts,
                session_id=session_id, cog=cog, from_phone=from_phone
            ))
            from scenario_data import is_nsfw_scenario
            if is_nsfw_scenario(scenario_key):
                self.add_item(IntimateProfileButton(
                    active_contact, scenario_key, user_id, contacts,
                    session_id=session_id, cog=cog, from_phone=from_phone
                ))

        # Phone-specific navigation items
        if from_phone and session_id:
            phone_row = 2
            if active_contact:
                contact_short = active_contact.get("name", "Contact")[:15]
                text_btn = discord.ui.Button(
                    label=f"Text {contact_short}",
                    emoji="💬",
                    style=discord.ButtonStyle.success,
                    row=phone_row
                )
                async def _on_text(inter: discord.Interaction):
                    from mechanics.system.phone import DMChatView, _build_dm_chat_embed
                    embed = _build_dm_chat_embed(session_id, active_contact)
                    view = DMChatView(cog, session_id, user_id, active_contact, contacts)
                    await inter.response.edit_message(embed=embed, view=view)
                text_btn.callback = _on_text
                self.add_item(text_btn)

                back_list_btn = discord.ui.Button(
                    label="Contact List",
                    emoji="👥",
                    style=discord.ButtonStyle.secondary,
                    row=phone_row
                )
                async def _on_back_list(inter: discord.Interaction):
                    char = await adb(db.get_character, user_id)
                    char_name = char.get("name", "Hero") if char else "Player"
                    list_embed = build_contact_list_embed(contacts, scenario_key, char_name)
                    list_view = ContactView(
                        contacts, scenario_key, user_id,
                        active_contact=None, page=self.page,
                        session_id=session_id, cog=cog, from_phone=True
                    )
                    await inter.response.edit_message(embed=list_embed, view=list_view)
                back_list_btn.callback = _on_back_list
                self.add_item(back_list_btn)

            home_btn = discord.ui.Button(
                label="Phone Home",
                emoji="📱",
                style=discord.ButtonStyle.secondary,
                row=phone_row
            )
            async def _on_home(inter: discord.Interaction):
                from mechanics.system.phone import PhoneMainView, build_phone_home_embed
                home_embed = build_phone_home_embed(session_id, user_id)
                home_view = PhoneMainView(cog, session_id, user_id)
                await inter.response.edit_message(embed=home_embed, view=home_view)
            home_btn.callback = _on_home
            self.add_item(home_btn)

        page_row = 3 if (from_phone and session_id) else 2
        if self.total_pages > 1:
            prev_btn = discord.ui.Button(label="◀️ Prev", style=discord.ButtonStyle.secondary, disabled=(self.page == 0), row=page_row)
            prev_btn.callback = self._on_prev
            self.add_item(prev_btn)

            page_label = discord.ui.Button(label=f"Page {self.page + 1}/{self.total_pages} ({len(contacts)} total)", style=discord.ButtonStyle.secondary, disabled=True, row=page_row)
            self.add_item(page_label)

            next_btn = discord.ui.Button(label="Next ▶️", style=discord.ButtonStyle.secondary, disabled=(self.page >= self.total_pages - 1), row=page_row)
            next_btn.callback = self._on_next
            self.add_item(next_btn)

    async def _on_prev(self, interaction: discord.Interaction):
        new_page = max(0, self.page - 1)
        new_view = ContactView(
            self.contacts, self.scenario_key, self.user_id,
            active_contact=self.active_contact, page=new_page,
            session_id=self.session_id, cog=self.cog, from_phone=self.from_phone
        )
        start = new_view.page * new_view.page_size
        embed = build_contact_detail_embed(self.contacts[start], self.scenario_key, user_id=self.user_id)
        await interaction.response.edit_message(embed=embed, view=new_view)

    async def _on_next(self, interaction: discord.Interaction):
        new_page = min(self.total_pages - 1, self.page + 1)
        new_view = ContactView(
            self.contacts, self.scenario_key, self.user_id,
            active_contact=self.active_contact, page=new_page,
            session_id=self.session_id, cog=self.cog, from_phone=self.from_phone
        )
        start = new_view.page * new_view.page_size
        embed = build_contact_detail_embed(self.contacts[start], self.scenario_key, user_id=self.user_id)
        await interaction.response.edit_message(embed=embed, view=new_view)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This contact view is for another player.", ephemeral=True)
            return False
        return True


def build_relations_embed(contact: dict, scenario_key: str = "fantasy", user_id: int = 0) -> discord.Embed:
    name = contact.get("name", "Unknown NPC")
    score = contact.get("relationship_score", 0)
    info_level = get_unlocked_info_level(score)

    reveal_debug = False
    if user_id:
        user_settings = db.get_settings(user_id)
        reveal_debug = bool(user_settings.get("debug_reveal_all_info"))

    import mechanics.social.genealogy as genealogy
    relations = genealogy.ensure_contact_relations(contact, session_id=contact.get("session_id", 0), scenario=scenario_key)

    disclosed = genealogy.format_relations_for_disclosure(relations, info_level=info_level, debug_reveal=reveal_debug)

    embed = discord.Embed(
        title=f"👑 Relations & Family Codex: {name}",
        description="*A persistent record of lineage, family tree, romantic standing, friends, and rivals.*",
        color=discord.Color.gold()
    )

    # 1. Family Tree
    fam_data = disclosed.get("family", {})
    if fam_data.get("revealed"):
        members = fam_data.get("members", [])
        fam_lines = []
        for m in members:
            rel = m.get("relation", "Relative")
            m_first = m.get("first_name", "").strip()
            m_last = m.get("surname", "").strip()
            fallback_name = f"{m_first} {m_last}".strip()
            m_name = m.get("name") or fallback_name or "Unknown"
            c_race = contact.get("race") or contact.get("basic_info", {}).get("race") or "Unknown"
            m_race = format_race_display(m.get("race") or c_race)
            m_status = m.get("status", "Alive")
            m_occ = m.get("occupation", "Citizen")
            status_emoji = "🟢" if str(m_status).lower() == "alive" else "💀"

            if "Father" in rel:
                r_emoji = "👨"
            elif "Mother" in rel:
                r_emoji = "👩"
            elif "Brother" in rel:
                r_emoji = "👦"
            elif "Sister" in rel:
                r_emoji = "👧"
            else:
                r_emoji = "👤"

            is_parent = any(p in rel for p in ("Father", "Mother", "Parent"))
            if is_parent:
                fam_lines.append(f"{r_emoji} **{rel}**: {m_name} ({m_race}) — {status_emoji}")
            else:
                occ_suffix = f" *{m_occ}*" if m_occ else ""
                fam_lines.append(f"{r_emoji} **{rel}**: {m_name} ({m_race}) — {status_emoji}{occ_suffix}")

        embed.add_field(
            name="👨‍👩‍👧‍👦 Immediate Family Tree",
            value="\n".join(fam_lines) if fam_lines else "*No immediate family members recorded.*",
            inline=False
        )
    else:
        embed.add_field(
            name="👨‍👩‍👧‍👦 Immediate Family Tree",
            value=f"*{fam_data.get('locked_message', '🔒 Family Tree guarded (Requires Level 3/3 Disclosure)')}*",
            inline=False
        )

    # 2. Romantic Standing
    rom_data = disclosed.get("romance", {})
    rom_lines = []

    c_part = rom_data.get("current_partner")
    if c_part:
        rom_lines.append(f"• **Current Partner**: 💖 {c_part.get('name')} (*{c_part.get('role', 'Partner')}*)")
    else:
        status_text = rom_data.get("status", "Single")
        rom_lines.append(f"• **Current Status**: {status_text}")

    s_part = rom_data.get("secret_partner")
    if s_part:
        if isinstance(s_part, dict) and s_part.get("locked"):
            rom_lines.append(f"• **Secret Affairs**: *{s_part.get('message', '🔒 Locked')}*")
        elif isinstance(s_part, dict) and s_part.get("name"):
            rom_lines.append(f"• **Secret Affair**: 🤫 {s_part.get('name')} (*{s_part.get('role', 'Secret Lover')}*)")

    ex_list = rom_data.get("ex_partners", [])
    if ex_list:
        ex_strs = []
        for ex in ex_list:
            if isinstance(ex, dict) and ex.get("locked"):
                ex_strs.append(f"*{ex.get('message', '🔒 Locked')}*")
            elif isinstance(ex, dict) and ex.get("name"):
                ex_strs.append(f"{ex.get('name')} (*{ex.get('role', 'Ex-Partner')}*)")
        if ex_strs:
            rom_lines.append(f"• **Past Ex-Partner(s)**: 💔 {', '.join(ex_strs)}")
    elif rom_data.get("revealed"):
        rom_lines.append("• **Past Ex-Partner(s)**: *None (No prior romantic partners)*")

    embed.add_field(
        name="💖 Romantic Standing",
        value="\n".join(rom_lines) if rom_lines else "*No romantic history disclosed.*",
        inline=False
    )

    # 3. Friends & Social Circle
    friend_data = disclosed.get("friends", {})
    f_members = friend_data.get("members", [])
    if f_members:
        f_lines = []
        for f in f_members:
            f_name = f.get('name')
            f_role = f.get('role')
            if f_role and f_role != "Friend":
                f_lines.append(f"• 🤝 **{f_name}** — *{f_role}*")
            else:
                f_lines.append(f"• 🤝 **{f_name}**")
        embed.add_field(
            name="🤝 Friends",
            value="\n".join(f_lines),
            inline=False
        )
    else:
        embed.add_field(
            name="🤝 Friends",
            value="*No close friends known.*",
            inline=False
        )

    # 4. Rivals & Adversaries
    rival_data = disclosed.get("rivals", {})
    r_members = rival_data.get("members", [])
    if r_members:
        r_lines = []
        for r in r_members:
            r_name = r.get('name')
            r_role = r.get('role')
            if r_role and r_role != "Rival":
                r_lines.append(f"• ⚔️ **{r_name}** — *{r_role}*")
            else:
                r_lines.append(f"• ⚔️ **{r_name}**")
        embed.add_field(
            name="⚔️ Rivals",
            value="\n".join(r_lines),
            inline=False
        )
    else:
        embed.add_field(
            name="⚔️ Rivals",
            value="*No known rivals.*",
            inline=False
        )

    footer_suffix = " • [🛠️ DEBUG: Revealed]" if reveal_debug else ""
    embed.set_footer(text=f"Information Disclosure Level: {info_level}/3 • Social Graph & Lineage Dossier{footer_suffix}")
    return embed


def build_romantic_memories_embed(contact: dict, scenario_key: str = "fantasy", user_id: int = 0) -> discord.Embed:
    name = contact.get("name", "Unknown NPC")
    memories = list(contact.get("intimate_memories", []))

    score = contact.get("relationship_score", 0)
    info_level = get_unlocked_info_level(score)

    reveal_debug = False
    if user_id:
        user_settings = db.get_settings(user_id)
        reveal_debug = bool(user_settings.get("debug_reveal_all_info"))

    intimate_unlocked = (
        (info_level >= 3)
        or contact.get("revealed_flags", {}).get("intimate_revealed", False)
        or contact.get("revealed_flags", {}).get("all_revealed", False)
        or contact.get("appearance", {}).get("intimate_revealed", False)
        or contact.get("appearance", {}).get("all_revealed", False)
        or reveal_debug
    )

    shared_milestones = [m for m in memories if not str(m).startswith("Past History:")]
    past_history = [m for m in memories if str(m).startswith("Past History:")]

    from mechanics.social.persona import generate_past_intimate_history, enforce_intimacy_safeguard_invariants
    import hashlib
    app_dict = dict(contact.get("appearance", {}))
    app_dict["intimate_memories"] = list(memories)
    app_dict = enforce_intimacy_safeguard_invariants(app_dict)

    if app_dict.get("had_first_time_with_player") and app_dict.get("intercourse_experience") == "non_virgin":
        past_history = ["Past History: Virgin (No prior intimate history before meeting you; shared first time with you)"]
    elif (reveal_debug or intimate_unlocked) and not past_history:
        i_exp = app_dict.get("intercourse_experience", "")
        o_exp = app_dict.get("oral_experience", "")
        m_exp = app_dict.get("manual_experience", "")
        open_val = app_dict.get("erotic_openness") or app_dict.get("openness") or "moderate"
        c_gender = contact.get("gender") or app_dict.get("gender") or contact.get("basic_info", {}).get("gender", "")
        c_race = contact.get("race") or app_dict.get("race") or contact.get("basic_info", {}).get("race", "")

        is_virgin_or_inexp = (not i_exp or i_exp in ("virgin", "inexperienced"))
        is_oral_inexp = (not o_exp or o_exp == "inexperienced")
        is_manual_inexp = (not m_exp or m_exp == "inexperienced")

        if not (is_virgin_or_inexp and is_oral_inexp and is_manual_inexp):
            seed_str = (name.strip() + "_past_history").encode("utf-8")
            h_val = int(hashlib.md5(seed_str).hexdigest(), 16)
            past_data = generate_past_intimate_history(
                hash_val=h_val,
                race=c_race,
                gender=c_gender,
                scenario=scenario_key,
                openness=open_val,
                intercourse=i_exp,
                oral=o_exp,
                manual=m_exp
            )
            if past_data and past_data.get("entries"):
                past_history = past_data["entries"]
            elif past_data:
                past_history = [past_data["entry"]]
            # Persist generated entries so they stabilize across repeated views
            if past_history:
                try:
                    sess_id = contact.get("session_id", 0)
                    char_id = contact.get("character_id", 0)
                    npc_id = contact.get("npc_id") or name.strip()
                    for ph_entry in past_history:
                        mem_str = str(ph_entry) if str(ph_entry).startswith("Past History:") else f"Past History: {ph_entry}"
                        db.upsert_contact(
                            session_id=sess_id,
                            character_id=char_id,
                            npc_id=npc_id,
                            name=name.strip(),
                            new_memory=mem_str,
                        )
                except Exception:
                    pass
        else:
            past_history = ["Past History: Virgin (No prior intimate history before meeting you)"]

    embed = discord.Embed(
        title=f"📖 Romantic Memories Journal: {name}",
        description="*A persistent record of shared milestones, dates, and background history.*",
        color=discord.Color.magenta()
    )

    if shared_milestones:
        mem_lines = [f"• {m}" for m in shared_milestones[:15]]
        embed.add_field(
            name="💖 Shared Romantic Milestones",
            value="\n".join(mem_lines),
            inline=False
        )
    else:
        embed.add_field(
            name="💖 Shared Romantic Milestones",
            value="*No romantic milestones shared with you yet. Build your relationship to unlock shared dates, first kisses, and intimate memories!*",
            inline=False
        )

    if past_history:
        clean_past = [str(m).replace("Past History:", "").strip() for m in past_history]
        embed.add_field(
            name="📜 Past Intimate History",
            value="\n".join(f"• {m}" for m in clean_past[:10]),
            inline=False
        )

    total_count = len(shared_milestones) + len(past_history)
    footer_suffix = " • [🛠️ DEBUG: Revealed]" if reveal_debug else ""
    embed.set_footer(text=f"Total Recorded Entries: {total_count} | Max Display: 20{footer_suffix}")
    return embed


def build_intimate_profile_embed(contact: dict, scenario_key: str = "fantasy", user_id: int = 0) -> discord.Embed:
    name = contact.get("name", "Unknown NPC")
    score = contact.get("relationship_score", 0)
    info_level = get_unlocked_info_level(score)

    reveal_debug = False
    if user_id:
        user_settings = db.get_settings(user_id)
        reveal_debug = bool(user_settings.get("debug_reveal_all_info"))

    from mechanics.social.persona import format_intimate_profile_sections, infer_contact_gender, normalize_appearance, enforce_intimacy_safeguard_invariants
    revealed_flags = dict(contact.get("revealed_flags", {}))
    app_data = dict(contact.get("appearance", {}))
    app_data["intimate_memories"] = contact.get("intimate_memories", [])
    app_data = enforce_intimacy_safeguard_invariants(app_data)
    if isinstance(app_data, dict):
        for flag_k in (
            "intimate_revealed", "intercourse_revealed",
            "oral_revealed", "manual_revealed", "demeanor_revealed",
            "dynamic_revealed", "openness_revealed",
            "sensitive_spots_revealed", "turn_ons_revealed", "fetishes_revealed",
            "act_preferences_revealed", "underwear_revealed", "mannerisms_revealed", "all_revealed"
        ):
            if app_data.get(flag_k):
                revealed_flags[flag_k] = True

    if reveal_debug:
        info_level = 3
        revealed_flags.update({
            "intimate_revealed": True,
            "all_revealed": True,
            "mannerisms_revealed": True,
            "intercourse_revealed": True,
            "oral_revealed": True,
            "manual_revealed": True,
            "demeanor_revealed": True,
            "dynamic_revealed": True,
            "openness_revealed": True,
            "sensitive_spots_revealed": True,
            "turn_ons_revealed": True,
            "fetishes_revealed": True,
            "underwear_revealed": True,
            "act_preferences_revealed": True
        })

    gender_val = infer_contact_gender(contact) or "female"
    basic = contact.get("basic_info", {})
    race_val = contact.get("race") or basic.get("race") or ""
    desc_val = basic.get("description", "")
    if isinstance(desc_val, dict):
        desc_val = " ".join(str(v) for v in desc_val.values() if v)
    traits = list(contact.get("unlocked_traits", [])) or list(contact.get("traits", []))

    norm_app = normalize_appearance(app_data, gender=gender_val, race=race_val or "", scen_key=scenario_key, desc=desc_val, traits=traits)
    sections = format_intimate_profile_sections(
        norm_app,
        gender=gender_val,
        race=race_val or "Unknown",
        scen_key=scenario_key,
        info_level=info_level,
        revealed_flags=revealed_flags
    )

    embed = discord.Embed(
        title=f"🔞 Intimate Profile: {name}",
        description="*A discreet dossier of intimate physical traits, demeanor, dynamic, and preferences.*",
        color=discord.Color.magenta()
    )

    # 1. Anatomy & Experience (inline=True)
    clean_anatomy = sections.get("anatomy", [])
    anatomy_val = "\n".join(clean_anatomy) if clean_anatomy else "*Unknown*"
    embed.add_field(
        name="🔞 Anatomy & Experience",
        value=anatomy_val,
        inline=True
    )

    # 2. Demeanor & Dynamic (inline=True)
    dyn_val = "\n".join(sections["dynamic"]) if sections.get("dynamic") else "*Unknown*"
    embed.add_field(
        name="🎭 Demeanor & Dynamic",
        value=dyn_val,
        inline=True
    )

    # 3. Undergarments (inline=False)
    under_val = "\n".join(sections.get("undergarments", [])) if sections.get("undergarments") else "*Unknown*"
    embed.add_field(
        name="👙 Undergarments",
        value=under_val,
        inline=False
    )

    # 4. Turn-Ons & Desires (inline=False)
    clean_sens = sections.get("sensitivities", [])
    sens_val = "\n".join(clean_sens) if clean_sens else "*Unknown*"
    embed.add_field(
        name="🔥 Turn-Ons & Desires",
        value=sens_val,
        inline=False
    )

    # 5. Act & Position Preferences (inline=False)
    act_val = "\n".join(sections["act_preferences"]) if sections.get("act_preferences") else "*Unknown*"
    embed.add_field(
        name="❤️ Act & Position Preferences",
        value=act_val,
        inline=False
    )

    footer_suffix = " • [🛠️ DEBUG: Revealed]" if reveal_debug else ""
    embed.set_footer(text=f"Information Disclosure Level: {info_level}/3 • Intimate Dossier{footer_suffix}")
    return embed


def build_contact_list_embed(contacts: list[dict], scenario_key: str, char_name: str) -> discord.Embed:
    icon, title = get_scenario_contact_title(scenario_key)
    embed = discord.Embed(
        title=f"{icon} {title}",
        description=f"Contacts and relationship standings for **{char_name}**.",
        color=discord.Color.blue()
    )

    if not contacts:
        embed.add_field(
            name="No Contacts Yet",
            value="You haven't met any notable NPCs in this adventure yet. Interact with characters to build your contact list!",
            inline=False
        )
        return embed

    for c in contacts[:15]:
        score = c.get("relationship_score", 0)
        track = c.get("track", "platonic")
        tier = get_relationship_tier(score, track, scenario_key)
        mod = get_relationship_modifier(score)
        mod_str = f"+{mod}" if mod > 0 else str(mod)
        name = c.get("name", "Unknown NPC")
        role = c.get("basic_info", {}).get("role") or c.get("basic_info", {}).get("occupation") or ""
        grade = c.get("basic_info", {}).get("grade") or ""
        grade_tag = f" [{grade}]" if grade else ""
        role_tag = f" — *{role}*" if role else ""
        bar = format_progress_bar(score, width=8)
        info_level = get_unlocked_info_level(score)

        status_line = f"Standing: **{tier['name']}** [{bar}] | Check Mod: `{mod_str}` | Info Lvl: `{info_level}/3`"
        traits = c.get("unlocked_traits", [])
        if traits:
            status_line += f"\nTraits: *{', '.join(traits[:2])}*"

        field_name = f"{tier.get('emoji', '👤')} {name[:60]}{grade_tag}{role_tag} ({track.capitalize()})"[:256]
        embed.add_field(
            name=field_name,
            value=status_line[:1024],
            inline=False
        )

    embed.set_footer(text=f"Total Contacts: {len(contacts)} | Use the menu below to view full details")
    return embed


def build_contact_detail_embed(contact: dict, scenario_key: str, user_id: int = 0) -> discord.Embed:
    score = contact.get("relationship_score", 0)
    track = contact.get("track", "platonic")
    tier = get_relationship_tier(score, track, scenario_key)
    modifier = get_relationship_modifier(score)
    mod_str = f"+{modifier}" if modifier > 0 else str(modifier)
    bar = format_progress_bar(score, width=12)

    name = contact.get("name", "Unknown NPC")
    basic = contact.get("basic_info", {})
    unlocked_traits = list(contact.get("unlocked_traits") or contact.get("traits") or [])
    preferences = list(contact.get("preferences") or [])
    info_level = get_unlocked_info_level(score)

    reveal_debug = False
    if user_id:
        user_settings = db.get_settings(user_id)
        reveal_debug = bool(user_settings.get("debug_reveal_all_info"))

    revealed_flags = dict(contact.get("revealed_flags", {}))
    app_data = contact.get("appearance", {})
    if isinstance(app_data, dict):
        for flag_k in (
            "intimate_revealed", "intercourse_revealed", "oral_revealed", "demeanor_revealed",
            "sensitive_spots_revealed", "turn_ons_revealed", "fetishes_revealed",
            "mannerisms_revealed", "all_revealed"
        ):
            if app_data.get(flag_k):
                revealed_flags[flag_k] = True

    if reveal_debug:
        info_level = 3
        revealed_flags.update({
            "intimate_revealed": True,
            "all_revealed": True,
            "mannerisms_revealed": True,
            "intercourse_revealed": True,
            "oral_revealed": True,
            "demeanor_revealed": True,
            "sensitive_spots_revealed": True,
            "turn_ons_revealed": True,
            "fetishes_revealed": True
        })
        if not unlocked_traits:
            unlocked_traits = contact.get("traits", []) or ["Observant", "Resourceful"]
        if not preferences:
            preferences = ["Likes Honesty", "Dislikes Arrogance"]

    embed = discord.Embed(
        title=f"👤 Contact Profile: {name}",
        color=discord.Color.gold() if score >= 31 else (discord.Color.red() if score < 0 else discord.Color.green())
    )

    embed.add_field(name="Relationship Standing", value=f"**{tier['name']}**\n`{bar}`", inline=True)
    embed.add_field(name="Social Track", value=f"`{track.capitalize()}`", inline=True)
    embed.add_field(name="Skill Check Modifier", value=f"`{mod_str}`", inline=True)

    # Basic Info
    from mechanics.social.races import format_race_display
    from mechanics.social.persona import (
        format_persona_embed_fields, infer_contact_gender,
        categorize_likes_and_dislikes, sanitize_npc_description
    )
    info_lines = []
    race_val = contact.get("race") or basic.get("race") or ""
    display_race = race_val if race_val else "Unknown"
    info_lines.append(f"• **Race**: {format_race_display(display_race)}")
    gender_val = infer_contact_gender(contact) or "female"
    info_lines.append(f"• **Gender**: {gender_val.capitalize()}")
    if basic.get("age"):
        info_lines.append(f"• **Age**: {basic['age']}")

    raw_faction = basic.get("faction") or basic.get("faction_affiliation") or basic.get("club") or contact.get("faction")
    is_affiliated = bool(raw_faction and str(raw_faction).strip().lower() not in ("none", "unaffiliated", "unknown", ""))

    if is_affiliated:
        faction_name = str(raw_faction).strip()
        club_role = basic.get("club_role")
        raw_role = basic.get("role") or basic.get("occupation") or club_role or "Member"
        role_val = str(raw_role).strip()
        if role_val.lower() in ("none", "unaffiliated", "unknown", ""):
            role_val = str(club_role).strip() if club_role and str(club_role).strip().lower() not in ("none", "unknown", "") else "Member"

        faction_display = faction_name
        if club_role and str(club_role).strip().lower() not in ("none", "unknown", ""):
            cr_str = str(club_role).strip()
            if cr_str.lower() not in faction_name.lower():
                faction_display = f"{faction_name} ({cr_str})"
    else:
        role_val = "None"
        faction_display = "None"

    is_school = "school" in scenario_key.lower() or "academy" in scenario_key.lower()
    grade_val = basic.get("grade") or basic.get("standing") or "None"

    if is_school:
        if is_affiliated and grade_val != "None":
            rank_label = "Club Member" if role_val.lower() in ("member", "club member", "none", "") else role_val
            grade_standing_display = f"{grade_val}, {rank_label}"
        else:
            grade_standing_display = grade_val
    else:
        # Non-school genres (Fantasy, Sci-Fi, Cyberpunk, etc.):
        # Reflect standing in the faction's established hierarchy
        if is_affiliated:
            standing_candidate = basic.get("standing")
            if standing_candidate and str(standing_candidate).strip().lower() not in ("none", "unknown", ""):
                grade_standing_display = str(standing_candidate).strip()
            elif role_val != "None":
                grade_standing_display = role_val
            elif grade_val != "None":
                grade_standing_display = grade_val
            else:
                grade_standing_display = "Member"
        else:
            grade_standing_display = basic.get("standing") or grade_val

    info_lines.append(f"• **Grade / Standing**: {grade_standing_display}")

    if is_affiliated:
        info_lines.append(f"• **Role**: {role_val}")
        info_lines.append(f"• **Faction Affiliation**: {faction_display}")
    else:
        info_lines.append("• **Faction Affiliation**: None")
        # Unaffiliated: Role is dynamically hidden from profile

    desc_raw = basic.get("description", "")
    desc_str = " ".join(str(v) for v in desc_raw.values() if v) if isinstance(desc_raw, dict) else str(desc_raw)
    clean_desc = sanitize_npc_description(desc_str) or "None"
    info_lines.append(f"• **Details**: {clean_desc}")

    embed.add_field(
        name="Basic Details",
        value="\n".join(info_lines) if info_lines else "*Basic public information.*",
        inline=False
    )

    # Physical Appearance & Mannerisms fields
    desc_val = clean_desc if clean_desc != "None" else ""
    mannerisms_val = contact.get("mannerisms") or basic.get("mannerisms") or ""
    app_fields = format_persona_embed_fields(
        contact.get("appearance", {}),
        gender=gender_val,
        race=race_val,
        scen_key=scenario_key,
        desc=desc_val,
        mannerisms=mannerisms_val,
        traits=unlocked_traits,
        info_level=info_level,
        revealed_flags=revealed_flags,
        include_intimate=False
    )
    for field in app_fields:
        embed.add_field(name=field["name"], value=field["value"], inline=field.get("inline", False))

    # Progressive disclosure: Traits (max 3), Likes (max 3), and Dislikes (max 3)
    from mechanics.combat.traits import get_trait

    likes_pool, dislikes_pool = categorize_likes_and_dislikes(
        preferences,
        traits=unlocked_traits,
        role=role_val if role_val != "None" else "",
        race=race_val,
        desc=desc_val
    )

    if reveal_debug:
        display_traits = unlocked_traits[:3]
        display_likes = likes_pool[:3]
        display_dislikes = dislikes_pool[:3]
    elif info_level == 1:
        display_traits = []
        display_likes = []
        display_dislikes = []
    elif info_level == 2:
        display_traits = unlocked_traits[:2]
        display_likes = []
        display_dislikes = []
    else:
        display_traits = unlocked_traits[:3]
        display_likes = likes_pool[:3]
        display_dislikes = dislikes_pool[:3]

    trait_lines = []
    for t_name in display_traits:
        t_def = get_trait(t_name)
        label = t_def["label"] if t_def and t_def.get("label") else t_name
        trait_lines.append(f"• **{label}**")

    like_lines = [f"• **{str(l_text).strip()}**" for l_text in display_likes]
    dislike_lines = [f"• **{str(d_text).strip()}**" for d_text in display_dislikes]

    embed.add_field(
        name="🧠 Unlocked Traits",
        value="\n".join(trait_lines) if trait_lines else "*0/3 traits discovered*",
        inline=False
    )

    embed.add_field(
        name="👍 Likes & Preferences",
        value="\n".join(like_lines) if like_lines else "*0/3 likes discovered*",
        inline=True
    )

    embed.add_field(
        name="👎 Dislikes",
        value="\n".join(dislike_lines) if dislike_lines else "*0/3 dislikes discovered*",
        inline=True
    )

    if reveal_debug:
        embed.set_footer(text=f"Information Disclosure Level: {info_level}/3 • [🛠️ DEBUG: Full Profile Revealed]")
    else:
        embed.set_footer(text=f"Information Disclosure Level: {info_level}/3")
    return embed


class ContactsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="contacts", description="View your contact list, relationship standings, and unlocked NPC traits.")
    async def contacts_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        character = await adb(db.get_character, interaction.user.id)
        if not character:
            await interaction.followup.send("You don't have an active character. Use `/character create` first!", ephemeral=True)
            return

        session_id = character.get("active_session_id")
        if not session_id:
            await interaction.followup.send("You are not currently in an active session.", ephemeral=True)
            return

        session = await adb(db.get_session, session_id)
        scenario_key = session.get("scenario", "fantasy") if session else "fantasy"

        if not (scenario_data.is_mechanic_enabled(scenario_key, "contact_list") or scenario_data.is_mechanic_enabled(scenario_key, "relationship_meter")):
            await interaction.followup.send("❌ The Contact List / Relationship mechanic is disabled for this scenario.", ephemeral=True)
            return

        contacts = await adb(db.get_contacts, session_id=session_id, character_id=character["id"])
        embed = build_contact_list_embed(contacts, scenario_key, character["name"])
        view = ContactView(contacts, scenario_key, interaction.user.id)

        await interaction.followup.send(embed=embed, view=view, ephemeral=True)



async def setup(bot: commands.Bot):
    await bot.add_cog(ContactsCog(bot))
