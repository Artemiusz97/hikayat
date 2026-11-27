"""
Discord Cog for viewing and managing NPC contacts & relationship meters.
"""
from __future__ import annotations

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
    get_unlocked_info_level, can_player_dm_contact
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


def filter_unlocked_contacts(
    contacts: list[dict],
    party_names: set[str],
    scenario_key: str,
    *,
    preloaded_session: dict | None = None,
    skip_session_lookup: bool = False,
) -> list[dict]:
    """Filters contacts down strictly to Friends (score >= 100), active party members, or explicitly added contacts.
    In High School scenarios, also requires peer/student eligibility.
    """
    from mechanics.social.relationships import is_contact_eligible, is_unlocked_contact
    from scenario_data import has_tag
    is_hs = has_tag(scenario_key, "high_school")
    is_anom = scenario_data.is_anomalous_incursions_scenario(scenario_key)
    unlocked = []
    for c in contacts:
        if not is_unlocked_contact(
            c,
            party_names,
            include_party=True,
            preloaded_session=preloaded_session,
            skip_session_lookup=skip_session_lookup,
        ):
            continue
        if is_hs or is_anom:
            b_info = c.get("basic_info") or {}
            r = b_info.get("role") or b_info.get("occupation") or ""
            d = b_info.get("description") or ""
            if not is_contact_eligible(
                name=c,
                role=r,
                description=d,
                scenario=scenario_key,
                preloaded_session=preloaded_session,
                skip_session_lookup=skip_session_lookup,
            ):
                continue
        unlocked.append(c)
    return unlocked


from cogs.contacts_routine_views import (
    build_acquaintance_detail_embed,
    build_acquaintances_list_embed,
    enrich_discord_npc_with_routine,
    format_discord_known_routine_value,
    format_discord_known_wardrobe_value,
    load_discord_contacts_and_acquaintances,
)
from mechanics.world.routine_disclosure import (
    apply_known_routine_to_contact,
    build_known_routine_payload,
)


class ContactSelect(discord.ui.Select):
    def __init__(self, page_contacts: list[dict], all_contacts: list[dict], scenario_key: str, page: int = 0, total_pages: int = 1,
                 session_id: int = 0, cog = None, from_phone: bool = False, party_names: set[str] | None = None,
                 acquaintances: list[dict] | None = None, fow_context: dict | None = None, char_name: str = "Hero"):
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
        self.party_names = party_names
        self.acquaintances = list(acquaintances or [])
        self.fow_context = fow_context
        self.char_name = str(char_name or "Hero")

    async def callback(self, interaction: discord.Interaction):
        npc_id = self.values[0]
        contact = self.contacts_dict.get(npc_id)
        if not contact:
            await interaction.response.send_message("Contact not found.", ephemeral=True)
            return

        embed = await adb(
            build_contact_detail_embed,
            contact,
            self.scenario_key,
            user_id=interaction.user.id,
            fow_context=self.fow_context,
        )
        new_view = ContactView(
            self.all_contacts, self.scenario_key, interaction.user.id,
            active_contact=contact, page=self.page,
            session_id=self.session_id, cog=self.cog, from_phone=self.from_phone,
            party_names=self.party_names,
            acquaintances=self.acquaintances,
            fow_context=self.fow_context,
            char_name=self.char_name,
        )
        await interaction.response.edit_message(embed=embed, view=new_view)


class RomanticMemoriesButton(discord.ui.Button):
    def __init__(self, contact: dict, scenario_key: str, user_id: int, contacts: list[dict],
                 session_id: int = 0, cog = None, from_phone: bool = False,
                 party_names: set[str] | None = None, acquaintances: list[dict] | None = None,
                 fow_context: dict | None = None, char_name: str = "Hero"):
        super().__init__(label="Romantic Memories", emoji="📖", style=discord.ButtonStyle.secondary, row=1)
        self.contact = contact
        self.scenario_key = scenario_key
        self.user_id = user_id
        self.contacts = contacts
        self.session_id = session_id
        self.cog = cog
        self.from_phone = from_phone
        self.party_names = party_names
        self.acquaintances = list(acquaintances or [])
        self.fow_context = fow_context
        self.char_name = str(char_name or "Hero")

    async def callback(self, interaction: discord.Interaction):
        embed = await adb(build_romantic_memories_embed, self.contact, scenario_key=self.scenario_key, user_id=self.user_id)
        view = RomanticMemoriesView(
            self.contact, self.scenario_key, self.user_id, self.contacts,
            session_id=self.session_id, cog=self.cog, from_phone=self.from_phone,
            party_names=self.party_names, acquaintances=self.acquaintances,
            fow_context=self.fow_context, char_name=self.char_name,
        )
        await interaction.response.edit_message(embed=embed, view=view)


class RelationsButton(discord.ui.Button):
    def __init__(self, contact: dict, scenario_key: str, user_id: int, contacts: list[dict],
                 session_id: int = 0, cog = None, from_phone: bool = False,
                 party_names: set[str] | None = None, acquaintances: list[dict] | None = None,
                 fow_context: dict | None = None, char_name: str = "Hero"):
        super().__init__(label="Relations & Family", emoji="👑", style=discord.ButtonStyle.secondary, row=1)
        self.contact = contact
        self.scenario_key = scenario_key
        self.user_id = user_id
        self.contacts = contacts
        self.session_id = session_id
        self.cog = cog
        self.from_phone = from_phone
        self.party_names = party_names
        self.acquaintances = list(acquaintances or [])
        self.fow_context = fow_context
        self.char_name = str(char_name or "Hero")

    async def callback(self, interaction: discord.Interaction):
        embed = await adb(build_relations_embed, self.contact, scenario_key=self.scenario_key, user_id=self.user_id)
        view = RelationsView(
            self.contact, self.scenario_key, self.user_id, self.contacts,
            session_id=self.session_id, cog=self.cog, from_phone=self.from_phone,
            party_names=self.party_names, acquaintances=self.acquaintances,
            fow_context=self.fow_context, char_name=self.char_name,
        )
        await interaction.response.edit_message(embed=embed, view=view)


class IntimateProfileButton(discord.ui.Button):
    def __init__(self, contact: dict, scenario_key: str, user_id: int, contacts: list[dict],
                 session_id: int = 0, cog = None, from_phone: bool = False,
                 party_names: set[str] | None = None, acquaintances: list[dict] | None = None,
                 fow_context: dict | None = None, char_name: str = "Hero"):
        super().__init__(label="Intimate Profile", emoji="🔞", style=discord.ButtonStyle.secondary, row=1)
        self.contact = contact
        self.scenario_key = scenario_key
        self.user_id = user_id
        self.contacts = contacts
        self.session_id = session_id
        self.cog = cog
        self.from_phone = from_phone
        self.party_names = party_names
        self.acquaintances = list(acquaintances or [])
        self.fow_context = fow_context
        self.char_name = str(char_name or "Hero")

    async def callback(self, interaction: discord.Interaction):
        embed = await adb(build_intimate_profile_embed, self.contact, scenario_key=self.scenario_key, user_id=self.user_id)
        view = IntimateProfileView(
            self.contact, self.scenario_key, self.user_id, self.contacts,
            session_id=self.session_id, cog=self.cog, from_phone=self.from_phone,
            party_names=self.party_names, acquaintances=self.acquaintances,
            fow_context=self.fow_context, char_name=self.char_name,
        )
        await interaction.response.edit_message(embed=embed, view=view)


class IntimateProfileView(discord.ui.View):
    def __init__(self, contact: dict, scenario_key: str, user_id: int, contacts: list[dict],
                 session_id: int = 0, cog = None, from_phone: bool = False,
                 party_names: set[str] | None = None, acquaintances: list[dict] | None = None,
                 fow_context: dict | None = None, char_name: str = "Hero"):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.add_item(BackToProfileButton(
            contact, scenario_key, user_id, contacts,
            session_id=session_id, cog=cog, from_phone=from_phone,
            party_names=party_names, acquaintances=acquaintances,
            fow_context=fow_context, char_name=char_name,
        ))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This contact view is for another player.", ephemeral=True)
            return False
        return True


class BackToProfileButton(discord.ui.Button):
    def __init__(self, contact: dict, scenario_key: str, user_id: int, contacts: list[dict],
                 session_id: int = 0, cog = None, from_phone: bool = False,
                 party_names: set[str] | None = None, acquaintances: list[dict] | None = None,
                 fow_context: dict | None = None, char_name: str = "Hero"):
        super().__init__(label="Back to Profile", emoji="🔙", style=discord.ButtonStyle.primary)
        self.contact = contact
        self.scenario_key = scenario_key
        self.user_id = user_id
        self.contacts = contacts
        self.session_id = session_id
        self.cog = cog
        self.from_phone = from_phone
        self.party_names = party_names
        self.acquaintances = list(acquaintances or [])
        self.fow_context = fow_context
        self.char_name = str(char_name or "Hero")

    async def callback(self, interaction: discord.Interaction):
        embed = await adb(
            build_contact_detail_embed,
            self.contact,
            self.scenario_key,
            user_id=self.user_id,
            fow_context=self.fow_context,
        )
        view = ContactView(
            self.contacts, self.scenario_key, self.user_id,
            active_contact=self.contact,
            session_id=self.session_id, cog=self.cog, from_phone=self.from_phone,
            party_names=self.party_names, acquaintances=self.acquaintances,
            fow_context=self.fow_context, char_name=self.char_name,
        )
        await interaction.response.edit_message(embed=embed, view=view)


class RomanticMemoriesView(discord.ui.View):
    def __init__(self, contact: dict, scenario_key: str, user_id: int, contacts: list[dict],
                 session_id: int = 0, cog = None, from_phone: bool = False,
                 party_names: set[str] | None = None, acquaintances: list[dict] | None = None,
                 fow_context: dict | None = None, char_name: str = "Hero"):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.add_item(BackToProfileButton(
            contact, scenario_key, user_id, contacts,
            session_id=session_id, cog=cog, from_phone=from_phone,
            party_names=party_names, acquaintances=acquaintances,
            fow_context=fow_context, char_name=char_name,
        ))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This contact view is for another player.", ephemeral=True)
            return False
        return True


class RelationsView(discord.ui.View):
    def __init__(self, contact: dict, scenario_key: str, user_id: int, contacts: list[dict],
                 session_id: int = 0, cog = None, from_phone: bool = False,
                 party_names: set[str] | None = None, acquaintances: list[dict] | None = None,
                 fow_context: dict | None = None, char_name: str = "Hero"):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.add_item(BackToProfileButton(
            contact, scenario_key, user_id, contacts,
            session_id=session_id, cog=cog, from_phone=from_phone,
            party_names=party_names, acquaintances=acquaintances,
            fow_context=fow_context, char_name=char_name,
        ))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This contact view is for another player.", ephemeral=True)
            return False
        return True


class WorldCodexButton(discord.ui.Button):
    def __init__(self, session_id: int, scenario_key: str, user_id: int, contacts: list[dict],
                 cog=None, from_phone: bool = False, row: int = 1,
                 party_names: set[str] | None = None, acquaintances: list[dict] | None = None,
                 fow_context: dict | None = None, char_name: str = "Hero"):
        super().__init__(label="World Codex", emoji="🌍", style=discord.ButtonStyle.secondary, row=row)
        self.session_id = session_id
        self.scenario_key = scenario_key
        self.user_id = user_id
        self.contacts = contacts
        self.cog = cog
        self.from_phone = from_phone
        self.party_names = party_names
        self.acquaintances = list(acquaintances or [])
        self.fow_context = fow_context
        self.char_name = str(char_name or "Hero")

    async def callback(self, interaction: discord.Interaction):
        char_name = self.char_name
        if not char_name or char_name == "Hero":
            char = await adb(db.get_character, self.user_id)
            char_name = char.get("name", "Hero") if char else "Player"
        embed, total_pages, _ = build_world_codex_embed(self.session_id, self.scenario_key, char_name, page=0)
        view = WorldCodexView(
            self.session_id, self.scenario_key, self.user_id, self.contacts,
            page=0, total_pages=total_pages, cog=self.cog, from_phone=self.from_phone,
            party_names=self.party_names, acquaintances=self.acquaintances,
            fow_context=self.fow_context, char_name=char_name,
        )
        await interaction.response.edit_message(embed=embed, view=view)


class WorldCodexView(discord.ui.View):
    def __init__(self, session_id: int, scenario_key: str, user_id: int, contacts: list[dict],
                 page: int = 0, total_pages: int = 1, cog=None, from_phone: bool = False,
                 party_names: set[str] | None = None, acquaintances: list[dict] | None = None,
                 fow_context: dict | None = None, char_name: str = "Hero"):
        super().__init__(timeout=180)
        self.session_id = session_id
        self.scenario_key = scenario_key
        self.user_id = user_id
        self.contacts = contacts
        self.page = page
        self.total_pages = total_pages
        self.cog = cog
        self.from_phone = from_phone
        self.party_names = party_names
        self.acquaintances = list(acquaintances or [])
        self.fow_context = fow_context
        self.char_name = str(char_name or "Hero")

        contacts_btn = discord.ui.Button(label="Personal Contacts", emoji="👥", style=discord.ButtonStyle.primary, row=0)
        async def _on_contacts(inter: discord.Interaction):
            char_name = self.char_name
            if not char_name or char_name == "Hero":
                char = await adb(db.get_character, self.user_id)
                char_name = char.get("name", "Hero") if char else "Player"
            c_embed = build_contact_list_embed(self.contacts, self.scenario_key, char_name, fow_context=self.fow_context)
            c_view = ContactView(
                self.contacts, self.scenario_key, self.user_id,
                session_id=self.session_id, cog=self.cog, from_phone=self.from_phone,
                party_names=self.party_names, acquaintances=self.acquaintances,
                fow_context=self.fow_context, char_name=char_name,
            )
            await inter.response.edit_message(embed=c_embed, view=c_view)
        contacts_btn.callback = _on_contacts
        self.add_item(contacts_btn)

        if total_pages > 1:
            prev_btn = discord.ui.Button(label="◀️ Prev", style=discord.ButtonStyle.secondary, disabled=(self.page == 0), row=1)
            prev_btn.callback = self._on_prev
            self.add_item(prev_btn)

            page_label = discord.ui.Button(label=f"Page {self.page + 1}/{total_pages}", style=discord.ButtonStyle.secondary, disabled=True, row=1)
            self.add_item(page_label)

            next_btn = discord.ui.Button(label="Next ▶️", style=discord.ButtonStyle.secondary, disabled=(self.page >= total_pages - 1), row=1)
            next_btn.callback = self._on_next
            self.add_item(next_btn)

    async def _on_prev(self, interaction: discord.Interaction):
        new_page = max(0, self.page - 1)
        char_name = self.char_name
        if not char_name or char_name == "Hero":
            char = await adb(db.get_character, self.user_id)
            char_name = char.get("name", "Hero") if char else "Player"
        embed, total_pages, _ = build_world_codex_embed(self.session_id, self.scenario_key, char_name, page=new_page)
        new_view = WorldCodexView(
            self.session_id, self.scenario_key, self.user_id, self.contacts,
            page=new_page, total_pages=total_pages, cog=self.cog, from_phone=self.from_phone,
            party_names=self.party_names, acquaintances=self.acquaintances,
            fow_context=self.fow_context, char_name=char_name,
        )
        await interaction.response.edit_message(embed=embed, view=new_view)

    async def _on_next(self, interaction: discord.Interaction):
        new_page = min(self.total_pages - 1, self.page + 1)
        char_name = self.char_name
        if not char_name or char_name == "Hero":
            char = await adb(db.get_character, self.user_id)
            char_name = char.get("name", "Hero") if char else "Player"
        embed, total_pages, _ = build_world_codex_embed(self.session_id, self.scenario_key, char_name, page=new_page)
        new_view = WorldCodexView(
            self.session_id, self.scenario_key, self.user_id, self.contacts,
            page=new_page, total_pages=total_pages, cog=self.cog, from_phone=self.from_phone,
            party_names=self.party_names, acquaintances=self.acquaintances,
            fow_context=self.fow_context, char_name=char_name,
        )
        await interaction.response.edit_message(embed=embed, view=new_view)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This codex view is for another player.", ephemeral=True)
            return False
        return True


class AcquaintanceSelect(discord.ui.Select):
    def __init__(
        self,
        page_acquaintances: list[dict],
        parent_view: "ContactView",
    ):
        self.parent_view = parent_view
        self.page_acquaintances = list(page_acquaintances)
        options = []
        for idx, acq in enumerate(self.page_acquaintances):
            name = str(acq.get("name") or "Unknown NPC")
            workplace = str(acq.get("workplace_label") or acq.get("role") or "Acquaintance")
            raw_aff = acq.get("affinity_score")
            if raw_aff is None:
                raw_aff = acq.get("relationship_score")
            if raw_aff is None:
                raw_aff = acq.get("affection")
            if raw_aff is None:
                raw_aff = acq.get("affinity")
            aff = int(raw_aff) if raw_aff is not None else 0
            desc = f"{workplace} | Aff {aff:+d} | DM Locked"
            options.append(discord.SelectOption(
                label=name[:100],
                value=f"acq_idx_{idx}",
                description=desc[:100],
                emoji="👥",
            ))
        super().__init__(
            placeholder=f"Inspect acquaintance... (Page {parent_view.acq_page + 1}/{parent_view.acq_total_pages})",
            min_values=1,
            max_values=1,
            options=options,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        chosen_val = self.values[0]
        chosen = None
        if chosen_val.startswith("acq_idx_"):
            try:
                idx = int(chosen_val.split("_")[-1])
            except (TypeError, ValueError):
                idx = -1
            if 0 <= idx < len(self.page_acquaintances):
                chosen = self.page_acquaintances[idx]
        if chosen is None:
            await interaction.response.send_message("Acquaintance not found.", ephemeral=True)
            return

        pv = self.parent_view
        reveal_debug = bool((pv.fow_context or {}).get("reveal_debug"))
        new_view = pv._clone_view(
            mode="acquaintances",
            active_contact=None,
            active_acquaintance=chosen,
        )
        embed = build_acquaintance_detail_embed(
            chosen,
            pv.scenario_key,
            pv.char_name,
            reveal_debug=reveal_debug,
        )
        await interaction.response.edit_message(embed=embed, view=new_view)


class ContactView(discord.ui.View):
    def __init__(self, contacts: list[dict], scenario_key: str, user_id: int,
                 active_contact: dict = None, page: int = 0,
                 session_id: int = 0, cog = None, from_phone: bool = False,
                 party_names: set[str] | None = None,
                 acquaintances: list[dict] | None = None,
                 mode: str = "contacts",
                 fow_context: dict | None = None,
                 active_acquaintance: dict | None = None,
                 acq_page: int = 0,
                 char_name: str = "Hero"):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.contacts = contacts
        self.scenario_key = scenario_key
        self.active_contact = active_contact
        self.page = page
        self.session_id = session_id
        self.cog = cog
        self.from_phone = from_phone
        self.fow_context = fow_context
        self.acquaintances = list(acquaintances or [])
        self.mode = mode if mode in ("contacts", "acquaintances") else "contacts"
        self.active_acquaintance = active_acquaintance
        self.acq_page = acq_page
        self.char_name = str(char_name or "Hero")

        if party_names is None and fow_context and fow_context.get("party_names") is not None:
            party_names = fow_context.get("party_names")
        elif party_names is None and from_phone and session_id:
            party_rows = db.get_session_party_npcs(session_id) or []
            party_names = {
                str(p.get("name") or "").strip().lower()
                for p in party_rows
                if str(p.get("name") or "").strip()
            }
        self.party_names: set[str] | None = (
            {str(p).strip().lower() for p in party_names if str(p).strip()}
            if party_names is not None
            else None
        )
        self.page_size = 25
        self.total_pages = max(1, (len(contacts) + self.page_size - 1) // self.page_size)
        self.acq_total_pages = max(1, (len(self.acquaintances) + self.page_size - 1) // self.page_size)

        if self.mode == "acquaintances":
            self._populate_acquaintances_mode()
        else:
            self._populate_contacts_mode()

    def _clone_view(
        self,
        *,
        active_contact: dict | None = None,
        page: int | None = None,
        mode: str | None = None,
        active_acquaintance: dict | None = None,
        acq_page: int | None = None,
    ) -> "ContactView":
        return ContactView(
            self.contacts,
            self.scenario_key,
            self.user_id,
            active_contact=active_contact,
            page=self.page if page is None else page,
            session_id=self.session_id,
            cog=self.cog,
            from_phone=self.from_phone,
            party_names=self.party_names,
            acquaintances=self.acquaintances,
            mode=self.mode if mode is None else mode,
            fow_context=self.fow_context,
            active_acquaintance=active_acquaintance,
            acq_page=self.acq_page if acq_page is None else acq_page,
            char_name=self.char_name,
        )

    def _populate_contacts_mode(self):
        contacts = self.contacts
        scenario_key = self.scenario_key
        user_id = self.user_id
        active_contact = self.active_contact
        session_id = self.session_id
        cog = self.cog
        from_phone = self.from_phone

        start = self.page * self.page_size
        end = start + self.page_size
        page_contacts = contacts[start:end]

        if contacts:
            self.add_item(ContactSelect(
                page_contacts, contacts, scenario_key, page=self.page, total_pages=self.total_pages,
                session_id=session_id, cog=cog, from_phone=from_phone, party_names=self.party_names,
                acquaintances=self.acquaintances, fow_context=self.fow_context, char_name=self.char_name,
            ))
        if active_contact:
            self.add_item(RelationsButton(
                active_contact, scenario_key, user_id, contacts,
                session_id=session_id, cog=cog, from_phone=from_phone,
                party_names=self.party_names, acquaintances=self.acquaintances,
                fow_context=self.fow_context, char_name=self.char_name,
            ))
            self.add_item(RomanticMemoriesButton(
                active_contact, scenario_key, user_id, contacts,
                session_id=session_id, cog=cog, from_phone=from_phone,
                party_names=self.party_names, acquaintances=self.acquaintances,
                fow_context=self.fow_context, char_name=self.char_name,
            ))
            from scenario_data import is_nsfw_scenario
            if is_nsfw_scenario(scenario_key):
                self.add_item(IntimateProfileButton(
                    active_contact, scenario_key, user_id, contacts,
                    session_id=session_id, cog=cog, from_phone=from_phone,
                    party_names=self.party_names, acquaintances=self.acquaintances,
                    fow_context=self.fow_context, char_name=self.char_name,
                ))

        if session_id and not from_phone:
            self.add_item(WorldCodexButton(
                session_id=session_id, scenario_key=scenario_key, user_id=user_id,
                contacts=contacts, cog=cog, from_phone=from_phone, row=1,
                party_names=self.party_names, acquaintances=self.acquaintances,
                fow_context=self.fow_context, char_name=self.char_name,
            ))

        acq_btn = discord.ui.Button(
            label=f"Acquaintances ({len(self.acquaintances)})",
            emoji="👥",
            style=discord.ButtonStyle.secondary,
            row=1,
        )
        acq_btn.callback = self._on_open_acquaintances
        self.add_item(acq_btn)

        # Phone-specific navigation items
        if from_phone and session_id:
            phone_row = 2
            if active_contact:
                _dm_allowed = can_player_dm_contact(
                    active_contact,
                    party_names=self.party_names,
                    scenario=scenario_key,
                    preloaded_session=(self.fow_context or {}).get("session"),
                    skip_session_lookup=bool(self.fow_context),
                )
                contact_short = active_contact.get("name", "Contact")[:15]
                text_btn = discord.ui.Button(
                    label=f"Text {contact_short}" if _dm_allowed else f"Text {contact_short} (No #)",
                    emoji="💬",
                    style=discord.ButtonStyle.success if _dm_allowed else discord.ButtonStyle.secondary,
                    disabled=not _dm_allowed,
                    row=phone_row
                )
                async def _on_text(inter: discord.Interaction):
                    from mechanics.system.phone import DMChatView, _build_dm_chat_embed
                    _sess_chk = await adb(db.get_session, session_id)
                    _party_chk = await adb(db.get_session_party_npcs, session_id)
                    _p_names_chk = {str(p.get("name", "")).strip().lower() for p in (_party_chk or [])}
                    if not can_player_dm_contact(active_contact, party_names=_p_names_chk, scenario=scenario_key):
                        await inter.response.send_message("You don't have their contact info yet. Exchange numbers or connect on PeerPulse first.", ephemeral=True)
                        return
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
                    char_name = char.get("name", "Hero") if char else self.char_name
                    list_embed = build_contact_list_embed(contacts, scenario_key, char_name, fow_context=self.fow_context)
                    list_view = self._clone_view(active_contact=None, mode="contacts")
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

    def _populate_acquaintances_mode(self):
        start = self.acq_page * self.page_size
        end = start + self.page_size
        page_acqs = self.acquaintances[start:end]

        if page_acqs:
            self.add_item(AcquaintanceSelect(page_acqs, self))

        contacts_btn = discord.ui.Button(
            label=f"Contacts ({len(self.contacts)})",
            emoji="💬",
            style=discord.ButtonStyle.primary,
            row=1,
        )
        contacts_btn.callback = self._on_open_contacts
        self.add_item(contacts_btn)

        if self.active_acquaintance:
            acq_list_btn = discord.ui.Button(
                label="Acquaintance List",
                emoji="👥",
                style=discord.ButtonStyle.secondary,
                row=1,
            )
            acq_list_btn.callback = self._on_open_acquaintances
            self.add_item(acq_list_btn)

        if self.session_id and not self.from_phone:
            self.add_item(WorldCodexButton(
                session_id=self.session_id,
                scenario_key=self.scenario_key,
                user_id=self.user_id,
                contacts=self.contacts,
                cog=self.cog,
                from_phone=self.from_phone,
                row=1,
                party_names=self.party_names,
                acquaintances=self.acquaintances,
                fow_context=self.fow_context,
                char_name=self.char_name,
            ))

        if self.active_acquaintance or (self.from_phone and self.session_id):
            action_row = 2
            if self.active_acquaintance:
                locked_btn = discord.ui.Button(
                    label="DM Locked (Acquaintance)",
                    emoji="🔒",
                    style=discord.ButtonStyle.secondary,
                    disabled=True,
                    row=action_row,
                )
                self.add_item(locked_btn)
            if self.from_phone and self.session_id:
                home_btn = discord.ui.Button(
                    label="Phone Home",
                    emoji="📱",
                    style=discord.ButtonStyle.secondary,
                    row=action_row,
                )
                async def _on_home(inter: discord.Interaction):
                    from mechanics.system.phone import PhoneMainView, build_phone_home_embed
                    home_embed = build_phone_home_embed(self.session_id, self.user_id)
                    home_view = PhoneMainView(self.cog, self.session_id, self.user_id)
                    await inter.response.edit_message(embed=home_embed, view=home_view)
                home_btn.callback = _on_home
                self.add_item(home_btn)

        page_row = 3 if (self.active_acquaintance or (self.from_phone and self.session_id)) else 2
        if self.acq_total_pages > 1:
            prev_btn = discord.ui.Button(label="◀️ Prev", style=discord.ButtonStyle.secondary, disabled=(self.acq_page == 0), row=page_row)
            prev_btn.callback = self._on_acq_prev
            self.add_item(prev_btn)

            page_label = discord.ui.Button(label=f"Page {self.acq_page + 1}/{self.acq_total_pages} ({len(self.acquaintances)} total)", style=discord.ButtonStyle.secondary, disabled=True, row=page_row)
            self.add_item(page_label)

            next_btn = discord.ui.Button(label="Next ▶️", style=discord.ButtonStyle.secondary, disabled=(self.acq_page >= self.acq_total_pages - 1), row=page_row)
            next_btn.callback = self._on_acq_next
            self.add_item(next_btn)

    async def _on_open_acquaintances(self, interaction: discord.Interaction):
        new_view = self._clone_view(
            mode="acquaintances",
            active_contact=None,
            active_acquaintance=None,
        )
        embed = build_acquaintances_list_embed(self.acquaintances, self.scenario_key, self.char_name)
        await interaction.response.edit_message(embed=embed, view=new_view)

    async def _on_open_contacts(self, interaction: discord.Interaction):
        new_view = self._clone_view(
            mode="contacts",
            active_contact=None,
            active_acquaintance=None,
        )
        embed = build_contact_list_embed(self.contacts, self.scenario_key, self.char_name, fow_context=self.fow_context)
        await interaction.response.edit_message(embed=embed, view=new_view)

    async def _on_acq_prev(self, interaction: discord.Interaction):
        new_page = max(0, self.acq_page - 1)
        new_view = self._clone_view(
            mode="acquaintances",
            active_contact=None,
            active_acquaintance=None,
            acq_page=new_page,
        )
        embed = build_acquaintances_list_embed(self.acquaintances, self.scenario_key, self.char_name)
        await interaction.response.edit_message(embed=embed, view=new_view)

    async def _on_acq_next(self, interaction: discord.Interaction):
        new_page = min(self.acq_total_pages - 1, self.acq_page + 1)
        new_view = self._clone_view(
            mode="acquaintances",
            active_contact=None,
            active_acquaintance=None,
            acq_page=new_page,
        )
        embed = build_acquaintances_list_embed(self.acquaintances, self.scenario_key, self.char_name)
        await interaction.response.edit_message(embed=embed, view=new_view)

    async def _on_prev(self, interaction: discord.Interaction):
        new_page = max(0, self.page - 1)
        new_view = self._clone_view(active_contact=self.active_contact, page=new_page, mode="contacts")
        start = new_view.page * new_view.page_size
        embed = await adb(
            build_contact_detail_embed,
            self.contacts[start],
            self.scenario_key,
            user_id=self.user_id,
            fow_context=self.fow_context,
        )
        await interaction.response.edit_message(embed=embed, view=new_view)

    async def _on_next(self, interaction: discord.Interaction):
        new_page = min(self.total_pages - 1, self.page + 1)
        new_view = self._clone_view(active_contact=self.active_contact, page=new_page, mode="contacts")
        start = new_view.page * new_view.page_size
        embed = await adb(
            build_contact_detail_embed,
            self.contacts[start],
            self.scenario_key,
            user_id=self.user_id,
            fow_context=self.fow_context,
        )
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


def _resolve_discord_masked_dossier(
    contact: dict,
    scenario_key: str,
    user_id: int = 0,
    fow_context: dict | None = None,
) -> tuple[dict, bool, str]:
    """Runs shared enrich_contact_dossier + Fog-of-War masking + known_routine for Discord."""
    from mechanics.social.relationships import enrich_contact_dossier

    c_in = dict(contact or {})
    reveal_debug = bool((fow_context or {}).get("reveal_debug"))
    ui_lang = str((fow_context or {}).get("ui_lang") or "en")
    sess_id = int(c_in.get("session_id") or (fow_context or {}).get("session_id") or 0)
    player_char: dict | None = dict((fow_context or {}).get("player_char") or {}) or None
    if fow_context is None and (user_id or sess_id or c_in.get("character_id")):
        if user_id:
            user_settings = db.get_settings(user_id) or {}
            reveal_debug = bool(user_settings.get("debug_reveal_all_info"))
            ui_lang = str(user_settings.get("ui_language") or "en")
        from mechanics.social.relationships import resolve_session_player_character

        char_row = resolve_session_player_character(
            session_id=sess_id,
            character_id=int(c_in.get("character_id") or 0),
            user_id=user_id,
        )
        if isinstance(char_row, dict):
            player_char = dict(char_row)
            if not c_in.get("character_id") and char_row.get("id"):
                c_in["character_id"] = int(char_row["id"])

    if fow_context is not None:
        enriched = enrich_discord_npc_with_routine(
            c_in,
            fow_context,
            is_acquaintance=bool(c_in.get("is_acquaintance")),
        )
        return enriched, reveal_debug, ui_lang

    enriched = enrich_contact_dossier(
        c_in,
        sess_id,
        scenario_key or "fantasy",
        debug_reveal_all=reveal_debug,
        lang=ui_lang,
        player_char=player_char,
    )
    if sess_id <= 0 and isinstance(c_in.get("known_routine"), dict):
        routine = dict(c_in["known_routine"])
    else:
        sess_row = db.get_session(sess_id) if sess_id > 0 else None
        s_day = int(sess_row.get("current_day") or 1) if isinstance(sess_row, dict) else None
        s_min = int(sess_row.get("current_minute")) if (isinstance(sess_row, dict) and sess_row.get("current_minute") is not None) else None
        routine = build_known_routine_payload(
            enriched,
            session_id=sess_id,
            scen_key=scenario_key or "fantasy",
            lang=ui_lang,
            debug_reveal_all=reveal_debug,
            character_id=int(c_in.get("character_id") or 0),
            fow_schedule_revealed=bool(enriched.get("schedule_revealed")),
            current_day=s_day,
            current_minute=s_min,
        )
    apply_known_routine_to_contact(enriched, routine, lang=ui_lang)
    return enriched, reveal_debug, ui_lang


def build_romantic_memories_embed(contact: dict, scenario_key: str = "fantasy", user_id: int = 0) -> discord.Embed:
    enriched_c, reveal_debug, _ = _resolve_discord_masked_dossier(contact, scenario_key, user_id)
    name = enriched_c.get("name", contact.get("name", "Unknown NPC"))
    shared_milestones = list(enriched_c.get("shared_romantic_milestones") or [])
    past_history = list(enriched_c.get("past_intimate_entries") or [])
    embed = discord.Embed(
        title=f"📖 Romantic Memories Journal: {name}",
        description="*A persistent record of shared milestones, dates, and background history.*",
        color=discord.Color.magenta(),
    )
    if shared_milestones:
        mem_lines = [f"• {m}" for m in shared_milestones[:15]]
        embed.add_field(
            name="💖 Shared Romantic Milestones",
            value="\n".join(mem_lines),
            inline=False,
        )
    else:
        embed.add_field(
            name="💖 Shared Romantic Milestones",
            value="*No romantic milestones shared with you yet. Build your relationship to unlock shared dates, first kisses, and intimate memories!*",
            inline=False,
        )
    if past_history:
        clean_past = [str(m).replace("Past History:", "").strip() for m in past_history]
        embed.add_field(
            name="📜 Past Intimate History",
            value="\n".join(f"• {m}" for m in clean_past[:10]),
            inline=False,
        )
    elif not enriched_c.get("intimate_dossier_revealed") and not reveal_debug:
        embed.add_field(
            name="📜 Past Intimate History",
            value="• ???",
            inline=False,
        )
    total_count = len(shared_milestones) + len(past_history)
    footer_suffix = " • [🛠️ DEBUG: Revealed]" if reveal_debug else ""
    embed.set_footer(text=f"Total Recorded Entries: {total_count} | Max Display: 20{footer_suffix}")
    return embed


def build_intimate_profile_embed(contact: dict, scenario_key: str = "fantasy", user_id: int = 0) -> discord.Embed:
    enriched_c, reveal_debug, _ = _resolve_discord_masked_dossier(contact, scenario_key, user_id)
    name = enriched_c.get("name", contact.get("name", "Unknown NPC"))
    score = int(enriched_c.get("relationship_score", contact.get("relationship_score", 0)) or 0)
    info_level = int(enriched_c.get("info_level") or get_unlocked_info_level(score))
    sections = dict(enriched_c.get("intimate_sections") or {})
    structured = dict(enriched_c.get("intimate_structured") or {})
    chemistry = dict(enriched_c.get("intimate_chemistry") or {})
    shared_stats = dict(enriched_c.get("shared_intimacy_stats") or {})

    embed = discord.Embed(
        title=f"🔞 Intimate Profile: {name}",
        description="*A discreet dossier of intimate physical traits, demeanor, dynamic, and preferences.*",
        color=discord.Color.magenta()
    )

    if chemistry.get("has_any"):
        chem_lines: list[str] = []
        if chemistry.get("best_approach"):
            chem_lines.append(str(chemistry["best_approach"]))
        if chemistry.get("body_match"):
            chem_lines.append(f"• **Physique**: {', '.join(chemistry['body_match'])}")
        if chemistry.get("act_alignment"):
            chem_lines.append(f"• **Synergy**: {', '.join(chemistry['act_alignment'])}")
        if chemistry.get("watch_out"):
            chem_lines.append(f"• **Avoid**: {', '.join(chemistry['watch_out'])}")
        if chem_lines:
            embed.add_field(
                name="✨ Chemistry & Synergy",
                value="\n".join(chem_lines),
                inline=False,
            )

    from mechanics.social import locales
    slot_mask = locales.get_masked_placeholder("slot", lang="en")

    # 1. Anatomy & Experience (inline=True)
    clean_anatomy = sections.get("anatomy", [])
    anatomy_val = "\n".join(clean_anatomy) if clean_anatomy else slot_mask
    embed.add_field(
        name="🔞 Anatomy & Experience",
        value=anatomy_val,
        inline=True
    )

    # 2. Demeanor & Dynamic (inline=True)
    dyn_lines_embed = [str(x) for x in (sections.get("dynamic") or [])]
    if structured and isinstance(structured.get("openness"), dict):
        dyn_lines_embed = [l for l in dyn_lines_embed if "**Openness**" not in l]
        _open_st = structured["openness"]
        _open_masked = bool(_open_st.get("masked"))
        _open_lbl = slot_mask if _open_masked else (_open_st.get("label") or slot_mask)
        _open_row = f"• **Openness**: {_open_lbl}"
        _comf_st = structured.get("with_you_comfort")
        if not _open_masked and isinstance(_comf_st, dict) and _comf_st.get("badge_label"):
            _open_row += f" • `{_comf_st['badge_label']}`"
        _cont_st = structured.get("openness_contrast")
        if not _open_masked and isinstance(_cont_st, dict) and _cont_st.get("label"):
            _open_row += f" • `{_cont_st['label']}`"
        dyn_lines_embed.append(_open_row)
    dyn_val = "\n".join(dyn_lines_embed) if dyn_lines_embed else slot_mask
    embed.add_field(
        name="🎭 Demeanor & Dynamic",
        value=dyn_val,
        inline=True
    )

    # 3. Undergarments (inline=False)
    under_val = "\n".join(sections.get("undergarments", [])) if sections.get("undergarments") else slot_mask
    embed.add_field(
        name="👙 Undergarments",
        value=under_val,
        inline=False
    )

    # 4. Sensitive Spots (inline=False)
    if structured.get("sensitive_spots"):
        _spot_tokens = [x["label"] if not x.get("masked") else slot_mask for x in structured["sensitive_spots"]]
        spots_val = f"• **Sensitive Spots**: {', '.join(_spot_tokens)}"
    else:
        clean_spots = sections.get("sensitive_spots", [])
        spots_val = "\n".join(clean_spots) if clean_spots else slot_mask
    embed.add_field(
        name="🌸 Sensitive Spots",
        value=spots_val,
        inline=False
    )

    # 5. Desires, Active Kink & Turn-Offs (inline=False)
    if structured:
        desire_lines_embed: list[str] = []
        if structured.get("desires"):
            _des_tokens = [x["label"] if not x.get("masked") else "???" for x in structured["desires"]]
            desire_lines_embed.append(f"• **Desires**: {', '.join(_des_tokens)}")
        if structured.get("active_kink"):
            _ak = structured["active_kink"]
            _ak_str = _ak["label"] if not _ak.get("masked") else "???"
            desire_lines_embed.append(f"• **Active Kink**: {_ak_str}")
        if structured.get("turn_offs"):
            _to_tokens = [x["label"] if not x.get("masked") else "???" for x in structured["turn_offs"]]
            desire_lines_embed.append(f"• **Turn-Offs**: {', '.join(_to_tokens)}")
        _bp_lbl_map = {
            "smaller_bb": "Smaller Breasts",
            "bigger_bb": "Bigger Breasts",
            "smaller_ass": "Smaller Rear",
            "bigger_ass": "Bigger Rear",
            "taller_partner": "Taller Partners",
            "shorter_partner": "Shorter Partners",
        }
        _bp_likes_st = [_bp_lbl_map[k] for k in (structured.get("body_likes") or []) if k in _bp_lbl_map]
        _bp_dislikes_st = [_bp_lbl_map[k] for k in (structured.get("body_dislikes") or []) if k in _bp_lbl_map]
        _bp_seg_st: list[str] = []
        if _bp_likes_st:
            _bp_seg_st.append("Likes " + ", ".join(_bp_likes_st))
        if _bp_dislikes_st:
            _bp_seg_st.append("Dislikes " + ", ".join(_bp_dislikes_st))
        if _bp_seg_st:
            desire_lines_embed.append(f"• **Body Preferences**: {'; '.join(_bp_seg_st)}")
        if not desire_lines_embed and (info_level >= 3 or reveal_debug):
            desire_lines_embed = ["• **Desires**: None", "• **Turn-Offs**: None"]
        desires_val = "\n".join(desire_lines_embed) if desire_lines_embed else slot_mask
    else:
        clean_desires = sections.get("desires_and_turn_offs", [])
        desires_val = "\n".join(clean_desires) if clean_desires else slot_mask
    embed.add_field(
        name="🔥 Desires & Turn-Offs",
        value=desires_val,
        inline=False
    )

    # 6. Act & Position Preferences (inline=False)
    if structured and (structured.get("act_likes") or structured.get("act_dislikes")):
        act_lines_embed: list[str] = []
        if structured.get("act_likes"):
            _al_tokens = [
                ("???" if x.get("masked") else (f"{x['label']} (Curious)" if x.get("curious") else x["label"]))
                for x in structured["act_likes"]
            ]
            act_lines_embed.append(f"• **Preferred / Likes**: {', '.join(_al_tokens)}")
        if structured.get("act_dislikes"):
            _ad_tokens = [x["label"] if not x.get("masked") else "???" for x in structured["act_dislikes"]]
            act_lines_embed.append(f"• **Aversions / Dislikes**: {', '.join(_ad_tokens)}")
        act_val = "\n".join(act_lines_embed)
    elif structured and (info_level >= 3 or reveal_debug):
        act_val = "• **Preferred / Likes**: None\n• **Aversions / Dislikes**: None"
    else:
        act_val = "\n".join(sections["act_preferences"]) if sections.get("act_preferences") else slot_mask
    embed.add_field(
        name="❤️ Act & Position Preferences",
        value=act_val,
        inline=False
    )

    if int(shared_stats.get("shared_encounters") or 0) > 0 or shared_stats.get("firsts_badges"):
        _sw_parts = [
            f"Shared Encounters: **{int(shared_stats.get('shared_encounters') or 0)}**",
            f"Partner Climaxes: **{int(shared_stats.get('partner_climaxes') or 0)}**",
        ]
        if shared_stats.get("firsts_badges"):
            _ft_str = ", ".join(f"First {t.title()} Together" for t in shared_stats["firsts_badges"])
            _sw_parts.append(f"Milestones: {_ft_str}")
        embed.add_field(
            name="💞 Shared With You",
            value="\n".join(f"• {p}" for p in _sw_parts),
            inline=False,
        )

    footer_suffix = " • [🛠️ DEBUG: Revealed]" if reveal_debug else ""
    embed.set_footer(text=f"Information Disclosure Level: {info_level}/3 • Intimate Dossier{footer_suffix}")
    return embed


def build_world_codex_embed(session_id: int, scenario_key: str, char_name: str, page: int = 0, page_size: int = 10) -> tuple[discord.Embed, int, list[dict]]:
    """Builds an embed listing all known/discovered people in the world from lorebook and contacts."""
    from mechanics.social.relationships import get_discovered_world_codex_persons
    unique_persons, contact_scores = get_discovered_world_codex_persons(session_id, scenario_key, char_name)

    total_pages = max(1, (len(unique_persons) + page_size - 1) // page_size)
    page = max(0, min(page, total_pages - 1))
    start = page * page_size
    page_items = unique_persons[start:start + page_size]

    embed = discord.Embed(
        title="🌍 World Codex: Discovered Characters & Lore",
        description=f"Record of all characters discovered by **{char_name}** across the world.\n*Detailed personal traits, romantic memories, and full profiles are unlocked exclusively for Friends (100+ Affinity) or Party Members in your Contacts list.*",
        color=discord.Color.teal()
    )

    if not page_items:
        embed.add_field(
            name="No Discovered People Yet",
            value="You haven't encountered any notable people in this world yet. Explore locations and converse with residents to populate your World Codex!",
            inline=False
        )
        return embed, total_pages, unique_persons

    for p in page_items:
        name = p.get("name", "Unknown")
        role = p.get("role") or p.get("occupation") or p.get("description") or "Citizen"
        race = p.get("race") or "Unknown"
        gender = p.get("gender") or "Unknown"
        score, track = contact_scores.get(name.lower(), (0, "platonic"))
        tier = get_relationship_tier(score, track, scenario_key)
        bar = format_progress_bar(score, width=8)

        anom_badge = ""
        if p.get("anomalous_npc_tag") == "special_agent":
            anom_badge = " `[⚡ Special Agent]`"
        elif p.get("anomalous_npc_tag") == "civilian":
            anom_badge = " `[👤 Civilian]`"
        if p.get("deceased"):
            anom_badge += " `[💀 Deceased]`"
        field_name = f"👤 {name}{anom_badge} — *{role}*"
        field_val = (
            f"• **Race**: {format_race_display(race)} | **Gender**: {gender.capitalize()}\n"
            f"• **Affinity**: {score} [{bar}] ({tier['name']})\n"
            f"• *🔒 Detailed Profile Locked (Requires Friend 100+ or Party Member)*"
        )
        embed.add_field(name=field_name[:256], value=field_val[:1024], inline=False)

    embed.set_footer(text=f"World Codex Page {page + 1}/{total_pages} • {len(unique_persons)} Discovered People")
    return embed, total_pages, unique_persons


def build_contact_list_embed(
    contacts: list[dict],
    scenario_key: str,
    char_name: str,
    fow_context: dict | None = None,
) -> discord.Embed:
    icon, title = get_scenario_contact_title(scenario_key)
    embed = discord.Embed(
        title=f"{icon} {title}",
        description=f"Personal contacts and relationship standings for **{char_name}**.",
        color=discord.Color.blue()
    )

    if not contacts:
        embed.add_field(
            name="No Personal Contacts Yet",
            value="You haven't unlocked any personal contacts yet. Ambient characters and strangers are recorded in the **World Codex**.\n\n"
                  "Raise an NPC's affinity to **Friend Tier (100+ Affinity)** or recruit them into your active party to unlock their full personal contact card!",
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
        if "schedule_revealed" not in c and not c.get("debug_revealed"):
            from mechanics.social.consequences import apply_fog_of_war_to_enriched_contact
            c = apply_fog_of_war_to_enriched_contact(
                c,
                session_id=int(c.get("session_id") or 0),
                character_id=int(c.get("character_id") or 0),
                is_nsfw=scenario_data.is_nsfw_scenario(scenario_key),
            )
        traits = c.get("unlocked_traits", [])
        if traits:
            status_line += f"\nTraits: *{', '.join(traits[:2])}*"

        anom_list_badge = ""
        import scenario_data as _sd_cl
        if _sd_cl.is_anomalous_incursions_scenario(scenario_key):
            try:
                from mechanics.social.anomalous_npc_tags import classify_anomalous_npc_tag
                c_tag = classify_anomalous_npc_tag(
                    c,
                    session_id=int(c.get("session_id") or (fow_context or {}).get("session_id") or 0),
                    scen_key=scenario_key,
                    read_only=bool(fow_context),
                    preloaded_agent_roster=(fow_context or {}).get("anomalous_agent_roster"),
                    preloaded_session=(fow_context or {}).get("session"),
                )
                anom_list_badge = " [⚡ Special Agent]" if c_tag == "special_agent" else " [👤 Civilian]"
                if (c.get("basic_info") or {}).get("deceased"):
                    anom_list_badge += " [💀 Deceased]"
            except Exception:
                pass
        field_name = f"{tier.get('emoji', '👤')} {name[:50]}{anom_list_badge}{grade_tag}{role_tag} ({track.capitalize()})"[:256]
        embed.add_field(
            name=field_name,
            value=status_line[:1024],
            inline=False
        )

    embed.set_footer(text=f"Total Contacts: {len(contacts)} | Use the menu below to view full details")
    return embed


def build_contact_detail_embed(
    contact: dict,
    scenario_key: str,
    user_id: int = 0,
    fow_context: dict | None = None,
) -> discord.Embed:
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
    enriched_c, _fow_reveal_debug, _ = _resolve_discord_masked_dossier(
        contact, scenario_key, user_id, fow_context=fow_context
    )
    info_level = get_unlocked_info_level(score)

    reveal_debug = _fow_reveal_debug
    if user_id and fow_context is None:
        user_settings = db.get_settings(user_id) or {}
        reveal_debug = bool(user_settings.get("debug_reveal_all_info"))

    revealed_flags = dict(contact.get("revealed_flags", {}))
    app_data = contact.get("appearance", {})
    if isinstance(app_data, dict):
        for flag_k in (
            "intimate_revealed", "intercourse_revealed", "oral_revealed", "manual_revealed", "anal_revealed", "demeanor_revealed",
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
            "manual_revealed": True,
            "anal_revealed": True,
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
    from mechanics.social.persona import (
        format_persona_embed_fields,
        infer_contact_gender,
        sanitize_npc_description,
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
    else:
        role_val = "None"
        faction_display = "None"

    is_school = "school" in scenario_key.lower() or "academy" in scenario_key.lower()
    grade_val = basic.get("grade") or basic.get("standing") or "None"

    if is_school:
        grade_display = grade_val
        info_lines.append(f"• **Grade**: {grade_display}")
    else:
        # Non-school genres (Fantasy, Sci-Fi, Cyberpunk, etc.):
        standing_candidate = basic.get("standing")
        if standing_candidate and str(standing_candidate).strip().lower() not in ("none", "unknown", ""):
            standing_display = str(standing_candidate).strip()
        elif is_affiliated and role_val != "None":
            standing_display = role_val
        elif grade_val != "None":
            standing_display = grade_val
        else:
            standing_display = "Member" if is_affiliated else "None"

        info_lines.append(f"• **Standing**: {standing_display}")

    info_lines.append(f"• **Faction Affiliation**: {faction_display}")
    if is_affiliated and role_val != "None":
        info_lines.append(f"• **Role**: {role_val}")
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

    import scenario_data as _sd_cd
    if _sd_cd.is_anomalous_incursions_scenario(scenario_key):
        try:
            from mechanics.social.anomalous_npc_tags import hydrate_anomalous_npc_profile, TAG_SPECIAL_AGENT
            sess_id_cd = int(contact.get("session_id") or (fow_context or {}).get("session_id") or 0)
            anom_source = enriched_c if enriched_c.get("anomalous_npc_tag") else contact
            anom_prof = hydrate_anomalous_npc_profile(
                anom_source,
                session_id=sess_id_cd,
                scen_key=scenario_key,
                read_only=bool(fow_context),
                preloaded_agent_roster=(fow_context or {}).get("anomalous_agent_roster"),
                preloaded_session=(fow_context or {}).get("session"),
            )
            is_dec_cd = bool(basic.get("deceased") or contact.get("deceased"))
            if anom_prof["anomalous_npc_tag"] == TAG_SPECIAL_AGENT:
                if enriched_c.get("anomalous_npc_tag") == TAG_SPECIAL_AGENT or fow_context is not None:
                    dos = enriched_c
                else:
                    from mechanics.social.relationships import enrich_contact_dossier
                    sess_obj_cd = db.get_session(sess_id_cd) if sess_id_cd else {}
                    dos = enrich_contact_dossier(
                        contact,
                        sess_id_cd,
                        (sess_obj_cd or {}).get("scenario", scenario_key or "anomalous_incursions"),
                        debug_reveal_all=bool(reveal_debug),
                        read_only=bool(fow_context),
                    )
                attr_disp = str(dos.get("attribute") or anom_prof.get("attribute") or "physical").title()
                arch_disp = str(dos.get("combat_archetype") or anom_prof.get("combat_archetype") or "vanguard").title()
                dossier_lines = [
                    "• **Classification**: ⚡ **Special Agent**" + (" *(💀 Deceased)*" if is_dec_cd else ""),
                    f"• **Rank & Class**: Tier {anom_prof['agent_tier']} {anom_prof['rank_title']} — *{anom_prof['agent_class']}*",
                    f"• **Stage 1 Resonance**: **{attr_disp}** Attribute • **{arch_disp}** Archetype",
                    f"• **Combat Vitals**: ❤️ `{anom_prof['hp']}/{anom_prof['max_hp']} HP` | 💙 `{anom_prof['mp']}/{anom_prof['max_mp']} MP`",
                ]
                if int(dos.get("dossier_stage", 1)) >= 2:
                    med_disp = str(dos.get("ability_medium") or anom_prof.get("ability_medium") or "direct_manifestation").replace("_", " ").title()
                    dossier_lines.append(f"• **Stage 2 Medium**: **{med_disp}**")
                    ab_list = dos.get("innate_ability_details") or anom_prof.get("innate_ability_details") or []
                    if ab_list:
                        ab_fmt = "\n".join(
                            f"  - {ab['emoji']} **{ab['name']}** (`{'3 Pips • 0 MP' if ab.get('is_ultimate') else str(ab.get('mp_cost', 0)) + ' MP'}` • {ab['tier_name']})"
                            for ab in ab_list
                        )
                        dossier_lines.append(f"• **Awakened 5-Skill Kit**:\n{ab_fmt}")
                else:
                    dossier_lines.append("• *🔒 Stage 2 Dossier Classified — Ability Medium & 5-Skill Kit unlock at Affinity 15+, Party Companion, or Same-Faction Colleague.*")
                embed.add_field(name="⚡ Operative Combat Dossier", value="\n".join(dossier_lines)[:1024], inline=False)
            else:
                civ_w = (anom_prof.get("weapon_profile") or {}).get("name", "Improvised Object")
                civ_lines = [
                    "• **Classification**: 👤 **Civilian**" + (" *(💀 Deceased)*" if is_dec_cd else ""),
                    "• **Vitals**: ❤️ `100/100 HP` | 💙 `0 MP (No Mana)`",
                    f"• **Self-Defense Fallback**: `{civ_w}` *(Weapon-only if forced to fight; no special abilities)*",
                    "• **Party Eligibility**: *Contact-only — Civilians cannot be recruited into field combat parties.*",
                ]
                embed.add_field(name="👤 Civilian Classification", value="\n".join(civ_lines)[:1024], inline=False)
        except Exception:
            pass

    # Physical Appearance & Mannerisms fields
    desc_val = clean_desc if clean_desc != "None" else ""
    mannerisms_val = contact.get("mannerisms") or basic.get("mannerisms") or ""
    if not _fow_reveal_debug:
        unlocked_traits = [t for t in (enriched_c.get("unlocked_traits") or []) if "?" not in str(t)]
        contact = {**contact, "appearance": enriched_c.get("appearance", {})}
        revealed_flags = dict(enriched_c.get("revealed_flags") or revealed_flags)
    _app_for_embed = dict(contact.get("appearance") or {})
    if enriched_c.get("known_wardrobe"):
        for _ok in ("outfit_style", "attire", "clothing"):
            _app_for_embed.pop(_ok, None)
    app_fields = format_persona_embed_fields(
        _app_for_embed,
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

    # Fog-of-War Dossier Masking: Traits, Likes, Dislikes & Schedule
    from mechanics.combat.traits import get_trait
    # enriched_c resolved above before mannerisms formatting
    display_traits = list(enriched_c.get("unlocked_traits") or [])[:3]
    display_likes = list(enriched_c.get("preferences") or [])[:3]
    display_dislikes = list(enriched_c.get("dislikes") or [])[:3]

    trait_lines = []
    for t_name in display_traits:
        t_str = str(t_name or "").strip()
        if not t_str:
            continue
        if t_str == "???" or "?" in t_str:
            trait_lines.append(f"• `{t_str}`")
        else:
            t_def = get_trait(t_str)
            label = t_def["label"] if t_def and t_def.get("label") else t_str
            trait_lines.append(f"• **{label}**")

    like_lines = [f"• `{str(l_text).strip()}`" if "?" in str(l_text) else f"• **{str(l_text).strip()}**" for l_text in display_likes if str(l_text).strip()]
    dislike_lines = [f"• `{str(d_text).strip()}`" if "?" in str(d_text) else f"• **{str(d_text).strip()}**" for d_text in display_dislikes if str(d_text).strip()]

    embed.add_field(
        name="🧠 Unlocked Traits",
        value="\n".join(trait_lines) if trait_lines else "• `???`",
        inline=False,
    )

    embed.add_field(
        name="👍 Likes & Preferences",
        value="\n".join(like_lines) if like_lines else "• `???`",
        inline=True,
    )

    embed.add_field(
        name="👎 Dislikes",
        value="\n".join(dislike_lines) if dislike_lines else "• `???`",
        inline=True,
    )

    routine_val = format_discord_known_routine_value(
        enriched_c.get("known_routine"),
        str(enriched_c.get("known_schedule") or ""),
    )
    if routine_val:
        embed.add_field(
            name="🕒 Schedule & Routine",
            value=routine_val,
            inline=False,
        )

    wardrobe_val = format_discord_known_wardrobe_value(
        enriched_c.get("known_wardrobe"),
        lang=str((fow_context or {}).get("ui_lang") or "en"),
    )
    if wardrobe_val:
        embed.add_field(
            name="👔 Known Wardrobe",
            value=wardrobe_val,
            inline=False,
        )

    recent_interactions = contact.get("recent_memories") or contact.get("rel_history") or (contact.get("appearance") or {}).get("recent_memories") or []
    if recent_interactions:
        rec_lines = [f"• {m}" for m in recent_interactions[-5:]]
        embed.add_field(
            name="📜 Recent Shared Interactions",
            value="\n".join(rec_lines),
            inline=False
        )

    if reveal_debug:
        embed.set_footer(text=f"Information Disclosure Level: {info_level}/3 • [🛠️ DEBUG: Full Profile Revealed]")
    else:
        embed.set_footer(text=f"Information Disclosure Level: {info_level}/3")
    return embed


def build_folklore_encyclopedia_embed(
    payload: dict,
    mode: str = "archive",
    tradition_key: str = "all",
    page: int = 0,
    page_size: int = 6,
) -> tuple[discord.Embed, int, list[dict]]:
    """Builds a paginated Discord embed for the Folklore Codex Archive or Session Field Log."""
    total_count = int(payload.get("total_folklore_count", 0) or 0)
    disc_count = int(payload.get("discovered_count", 0) or 0)
    ver_count = int(payload.get("verified_count", 0) or 0)
    cont_count = int(payload.get("contained_count", 0) or 0)

    if mode == "sites":
        site_reg = payload.get("site_registry") if isinstance(payload.get("site_registry"), dict) else {}
        s_cards = list(site_reg.get("sites") or [])
        stab_c = int(site_reg.get("stabilized_count", 0) or 0)
        tot_c = int(site_reg.get("total_sites", 36) or 36)
        ch_rem = int(site_reg.get("resonator_charges_remaining", 0) or 0)
        ch_max = int(site_reg.get("resonator_charges_max", 3) or 3)
        ms_parts = [
            f"{'✓ ' if m.get('unlocked') else ''}{m.get('threshold')}/{tot_c}"
            for m in (site_reg.get("milestones") or [])
            if isinstance(m, dict)
        ]
        ms_line = " • **Milestones**: " + " | ".join(ms_parts) if ms_parts else ""

        total_pages = max(1, (len(s_cards) + page_size - 1) // page_size)
        page = max(0, min(page, total_pages - 1))
        start = page * page_size
        page_items = s_cards[start : start + page_size]

        embed = discord.Embed(
            title="🛡️ Quarantine Site Reclamation Grid",
            description=(
                f"**Stabilized Sites**: {stab_c}/{tot_c} • **Resonator Charges**: {ch_rem}/{ch_max}"
                f"{ms_line}"
            ),
            color=discord.Color.teal(),
        )
        if not page_items:
            embed.add_field(
                name="No Quarantine Sites Tracked",
                value="Quarantine site tracking activates inside Anomalous Incursions and Anomalous High scenarios.",
                inline=False,
            )
        else:
            for sc in page_items:
                s_name = str(sc.get("name") or sc.get("site_id") or "Site")
                s_badge = str(sc.get("badge") or "")
                s_rule = str(sc.get("domain_rule_name") or "")
                s_amb = str(sc.get("ambient_summary") or "")
                val_lines = [f"• **Status**: {s_badge}"] if s_badge else []
                if s_rule:
                    val_lines.append(f"• **Domain Rule**: {s_rule}")
                if s_amb:
                    val_lines.append(f"• {s_amb[:220]}")
                embed.add_field(
                    name=f"{s_name}"[:256],
                    value="\n".join(val_lines)[:1024] or "Status pending.",
                    inline=False,
                )
        embed.set_footer(text=f"Quarantine Site Grid • Page {page + 1}/{total_pages} • {len(s_cards)} Sites")
        return embed, total_pages, s_cards

    if mode == "field_log":
        items = list(payload.get("field_log") or [])
        total_pages = max(1, (len(items) + page_size - 1) // page_size)
        page = max(0, min(page, total_pages - 1))
        start = page * page_size
        page_items = items[start : start + page_size]
        vault_count = len(payload.get("vault_log") or [])
        req_count = len(payload.get("vault_requisitions") or [])

        embed = discord.Embed(
            title="📋 Session Anomaly Field Log",
            description=(
                f"Active & recorded session anomalies • **Field Entries**: {len(items)} • "
                f"**Contained**: {vault_count} • **Vault Requisitions**: {req_count}"
            ),
            color=discord.Color.dark_gold(),
        )
        if not page_items:
            embed.add_field(
                name="No Field Log Entries Yet",
                value="Encounter, scan, or contain anomalies during an active session to populate your Field Log.",
                inline=False,
            )
        else:
            for fl in page_items:
                fl_name = str(fl.get("name") or fl.get("public_name") or "Unknown Anomaly")
                fl_stage = str(fl.get("stage") or "sighted").capitalize()
                fl_loc = str(fl.get("location") or "Unknown Sector")
                fl_turn = fl.get("turn_updated") or fl.get("first_turn") or 0
                fl_omen = str(fl.get("sensory_omen") or fl.get("description") or "No telemetry recorded.")
                embed.add_field(
                    name=f"📡 {fl_name} [{fl_stage}]"[:256],
                    value=f"• **Location**: {fl_loc} (Turn {fl_turn})\n• {fl_omen}"[:1024],
                    inline=False,
                )
        embed.set_footer(text=f"Session Field Log • Page {page + 1}/{total_pages} • {len(items)} Entries")
        return embed, total_pages, items

    all_cards = list(payload.get("folklore_codex") or [])
    if tradition_key and tradition_key != "all":
        items = [c for c in all_cards if c.get("tradition_key") == tradition_key]
    else:
        items = all_cards

    total_pages = max(1, (len(items) + page_size - 1) // page_size)
    page = max(0, min(page, total_pages - 1))
    start = page * page_size
    page_items = items[start : start + page_size]

    trad_title = "All Traditions"
    for tr in (payload.get("traditions") or []):
        if str(tr.get("key") or "") == tradition_key:
            trad_title = f"{tr.get('emoji', '📖')} {tr.get('label', tradition_key)}"
            break

    embed = discord.Embed(
        title="📖 Folklore Codex & Anomaly Encyclopedia",
        description=(
            f"**Filter**: {trad_title}\n"
            f"**Discovered**: {disc_count}/{total_count} • **Verified**: {ver_count} • **Contained**: {cont_count}"
        ),
        color=discord.Color.dark_purple(),
    )

    if not page_items:
        embed.add_field(
            name="No Entries Found",
            value="No folklore records match the selected tradition filter.",
            inline=False,
        )
    else:
        for card in page_items:
            stage = str(card.get("unlock_stage") or "undiscovered")
            trad_lbl = card.get("tradition_label") or card.get("tradition") or "Unknown"
            if stage == "undiscovered":
                fname = f"❓ ??? — *{card.get('subtitle', 'Unencountered Folklore Record')}*"
                fval = (
                    f"• **Tradition**: {trad_lbl} | **Tier**: {card.get('min_tier', 1)}–{card.get('max_tier', 5)}\n"
                    f"• *{card.get('hint', '')}*"
                )
            else:
                badge = "🔒 Contained" if stage == "contained" else ("✅ Verified" if stage == "verified" else "👁️ Sighted")
                fname = f"{badge} | {card.get('name', 'Unknown')} — *{card.get('subtitle', '')}*"
                lines = [
                    f"• **Tradition**: {trad_lbl} | **Form**: {card.get('form_label', card.get('type', 'entity'))} | **Sightings**: {card.get('times_sighted', 1)}"
                ]
                if card.get("sensory_omen"):
                    lines.append(f"• **Omen**: {str(card['sensory_omen'])[:220]}")
                if card.get("is_verified"):
                    if card.get("taboo_rule"):
                        lines.append(f"• **Taboo**: {str(card['taboo_rule'])[:220]}")
                    if card.get("containment_protocol"):
                        lines.append(f"• **Protocol**: {str(card['containment_protocol'])[:220]}")
                else:
                    lines.append(f"• *{card.get('lore_summary', '[UNVERIFIED]')}*")
                fval = "\n".join(lines)
            embed.add_field(name=fname[:256], value=fval[:1024], inline=False)

    embed.set_footer(text=f"Folklore Archive • Page {page + 1}/{total_pages} • {len(items)} Entries")
    return embed, total_pages, items


class FolkloreTraditionSelect(discord.ui.Select):
    def __init__(self, parent_view: "FolkloreEncyclopediaView"):
        self.parent_view = parent_view
        payload = parent_view.payload
        options = [
            discord.SelectOption(
                label="All Traditions",
                description=f"{payload.get('discovered_count', 0)}/{payload.get('total_folklore_count', 0)} discovered",
                value="all",
                emoji="🌍",
                default=(parent_view.tradition_key == "all"),
            )
        ]
        for tr in (payload.get("traditions") or [])[:24]:
            t_key = str(tr.get("key") or "")
            if not t_key:
                continue
            options.append(
                discord.SelectOption(
                    label=str(tr.get("label") or t_key)[:100],
                    description=f"{tr.get('discovered', 0)}/{tr.get('total', 0)} discovered • {tr.get('contained', 0)} contained"[:100],
                    value=t_key[:100],
                    emoji=tr.get("emoji") or "📖",
                    default=(parent_view.tradition_key == t_key),
                )
            )
        super().__init__(placeholder="Filter by Folklore Tradition...", min_values=1, max_values=1, options=options, row=0)

    async def callback(self, interaction: discord.Interaction):
        chosen = self.values[0]
        embed, _, _ = build_folklore_encyclopedia_embed(
            self.parent_view.payload,
            mode="archive",
            tradition_key=chosen,
            page=0,
            page_size=self.parent_view.page_size,
        )
        new_view = FolkloreEncyclopediaView(
            payload=self.parent_view.payload,
            user_id=self.parent_view.user_id,
            session_id=self.parent_view.session_id,
            cog=self.parent_view.cog,
            from_phone=self.parent_view.from_phone,
            mode="archive",
            tradition_key=chosen,
            page=0,
            page_size=self.parent_view.page_size,
        )
        await interaction.response.edit_message(embed=embed, view=new_view)


class FolkloreEncyclopediaView(discord.ui.View):
    def __init__(
        self,
        payload: dict,
        user_id: int,
        session_id: int | None = None,
        cog=None,
        from_phone: bool = False,
        mode: str = "archive",
        tradition_key: str = "all",
        page: int = 0,
        page_size: int = 6,
    ):
        super().__init__(timeout=240)
        self.payload = payload or {}
        self.user_id = user_id
        self.session_id = session_id
        self.cog = cog
        self.from_phone = from_phone
        self.mode = mode if mode in ("archive", "field_log", "sites") else "archive"
        self.tradition_key = tradition_key or "all"
        self.page_size = max(1, int(page_size or 6))

        _, total_pages, _ = build_folklore_encyclopedia_embed(
            self.payload,
            mode=self.mode,
            tradition_key=self.tradition_key,
            page=page,
            page_size=self.page_size,
        )
        self.total_pages = total_pages
        self.page = max(0, min(int(page or 0), self.total_pages - 1))

        if self.mode == "archive" and (self.payload.get("traditions") or []):
            self.add_item(FolkloreTraditionSelect(self))

        nav_row = 1
        prev_btn = discord.ui.Button(
            label="◀️ Prev",
            style=discord.ButtonStyle.secondary,
            disabled=(self.page <= 0),
            row=nav_row,
        )
        prev_btn.callback = self._on_prev
        self.add_item(prev_btn)

        next_btn = discord.ui.Button(
            label="Next ▶️",
            style=discord.ButtonStyle.secondary,
            disabled=(self.page >= self.total_pages - 1),
            row=nav_row,
        )
        next_btn.callback = self._on_next
        self.add_item(next_btn)

        toggle_label = "Session Field Log" if self.mode == "archive" else "Folklore Archive"
        toggle_emoji = "📋" if self.mode == "archive" else "📖"
        toggle_btn = discord.ui.Button(
            label=toggle_label,
            emoji=toggle_emoji,
            style=discord.ButtonStyle.primary,
            row=nav_row,
        )
        toggle_btn.callback = self._on_toggle_mode
        self.add_item(toggle_btn)

        if bool((self.payload.get("site_registry") or {}).get("sites")):
            sites_btn = discord.ui.Button(
                label="Quarantine Sites",
                emoji="🛡️",
                style=discord.ButtonStyle.success if self.mode == "sites" else discord.ButtonStyle.secondary,
                row=nav_row,
            )
            sites_btn.callback = self._on_toggle_sites
            self.add_item(sites_btn)

        if self.from_phone and self.session_id:
            home_btn = discord.ui.Button(
                label="Phone Home",
                emoji="📱",
                style=discord.ButtonStyle.secondary,
                row=nav_row,
            )
            home_btn.callback = self._on_phone_home
            self.add_item(home_btn)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This encyclopedia view belongs to another player.", ephemeral=True)
            return False
        return True

    async def _refresh(self, interaction: discord.Interaction, *, mode: str, page: int):
        embed, _, _ = build_folklore_encyclopedia_embed(
            self.payload,
            mode=mode,
            tradition_key=self.tradition_key,
            page=page,
            page_size=self.page_size,
        )
        new_view = FolkloreEncyclopediaView(
            payload=self.payload,
            user_id=self.user_id,
            session_id=self.session_id,
            cog=self.cog,
            from_phone=self.from_phone,
            mode=mode,
            tradition_key=self.tradition_key,
            page=page,
            page_size=self.page_size,
        )
        await interaction.response.edit_message(embed=embed, view=new_view)

    async def _on_prev(self, interaction: discord.Interaction):
        await self._refresh(interaction, mode=self.mode, page=max(0, self.page - 1))

    async def _on_next(self, interaction: discord.Interaction):
        await self._refresh(interaction, mode=self.mode, page=min(self.total_pages - 1, self.page + 1))

    async def _on_toggle_mode(self, interaction: discord.Interaction):
        next_mode = "field_log" if self.mode == "archive" else "archive"
        await self._refresh(interaction, mode=next_mode, page=0)

    async def _on_toggle_sites(self, interaction: discord.Interaction):
        next_mode = "archive" if self.mode == "sites" else "sites"
        await self._refresh(interaction, mode=next_mode, page=0)

    async def _on_phone_home(self, interaction: discord.Interaction):
        from mechanics.system.phone import PhoneMainView, build_phone_home_embed
        home_embed = await adb(build_phone_home_embed, int(self.session_id), self.user_id)
        home_view = PhoneMainView(self.cog, int(self.session_id), self.user_id)
        await interaction.response.edit_message(embed=home_embed, view=home_view)


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

        party_npcs = await adb(db.get_session_party_npcs, session_id)
        party_names = {p.get("name", "").lower() for p in (party_npcs or []) if p.get("name")}
        unlocked_contacts, acquaintances, fow_context = await adb(
            load_discord_contacts_and_acquaintances,
            session_id,
            character["id"],
            scenario_key,
            user_id=interaction.user.id,
            party_names=party_names,
            party_npcs=party_npcs,
            filter_unlocked_fn=filter_unlocked_contacts,
            preloaded_session=session,
        )
        embed = build_contact_list_embed(unlocked_contacts, scenario_key, character["name"], fow_context=fow_context)
        view = ContactView(
            unlocked_contacts,
            scenario_key,
            interaction.user.id,
            session_id=session_id,
            cog=self,
            party_names=party_names,
            acquaintances=acquaintances,
            fow_context=fow_context,
            char_name=character["name"],
        )

        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="codex", description="Open your Codex: browse personal contacts (Friends/Party) or World Lore (Known NPCs).")
    async def codex_cmd(self, interaction: discord.Interaction):
        await self.contacts_cmd(interaction)

    @app_commands.command(name="encyclopedia", description="Browse your progressive Folklore Codex Archive and active Session Field Log.")
    async def encyclopedia_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        from mechanics.world.folklore_codex import build_encyclopedia_payload

        character = await adb(db.get_character, interaction.user.id)
        session_id = character.get("active_session_id") if character else None
        settings = await adb(db.get_settings, interaction.user.id)
        ui_lang = (settings or {}).get("ui_language") if isinstance(settings, dict) else None

        payload = await adb(
            build_encyclopedia_payload,
            session_id=session_id,
            user_id=interaction.user.id,
            lang=ui_lang,
        )
        embed, _, _ = build_folklore_encyclopedia_embed(payload, mode="archive", tradition_key="all", page=0)
        view = FolkloreEncyclopediaView(
            payload=payload,
            user_id=interaction.user.id,
            session_id=session_id,
            cog=self,
            from_phone=False,
        )
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)



async def setup(bot: commands.Bot):
    await bot.add_cog(ContactsCog(bot))
