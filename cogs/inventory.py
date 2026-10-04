from __future__ import annotations
"""
Interactive Discord Cog for Inventory & Gear Management.
Provides a live, interactive UI dashboard with in-place embed updates,
direct item equipping, slot unequipping, item dropping, and out-of-combat consumable usage.
"""
import discord
from discord import app_commands
from discord.ext import commands

import db
from db import adb
import character_data as cd
from character_data import (
    EQUIPMENT_SLOTS,
    EQUIPMENT_SLOT_EMOJI,
    DEFAULT_EQUIP_SLOT_FOR_ITEM_TYPE,
    inventory_capacity,
    get_item_icon
)
from mechanics.combat.items import apply_item_to_target, parse_item_effect


def build_inventory_embed(user_id: int, feedback_notice: str = "") -> discord.Embed:
    """Builds the rich inventory embed showing stats, equipped gear, and carried items."""
    char = db.get_character(user_id)
    if not char:
        return discord.Embed(title="No Character", description="You don't have an active character yet.", color=discord.Color.red())

    inv = db.get_inventory(user_id)
    cap = inventory_capacity(char["str_"])
    used_slots = sum(i.get("slot_cost", 1) for i in inv)

    embed = discord.Embed(
        title=f"🎒 {char['name']}'s Inventory ({used_slots}/{cap} slots used)",
        color=discord.Color.dark_green()
    )

    if feedback_notice:
        embed.description = f"{feedback_notice}\n"
    else:
        embed.description = f"❤️ **{char['hp']}/{char['max_hp']}** | 💙 **{char['mp']}/{char['max_mp']}** | 🪙 **{char.get('gold', 0)} Gold**\n"

    if not inv:
        embed.description += "\n*Your inventory is currently empty.*"
        embed.set_footer(text="Use the buttons below to manage your inventory & gear.")
        return embed

    # Group duplicate items
    grouped = {}
    for item in inv:
        key = (
            item["name"],
            item.get("item_type", "Item"),
            item.get("effect", ""),
            bool(item.get("equipped")),
            item.get("slot", "")
        )
        if key not in grouped:
            grouped[key] = {
                "item": item,
                "count": 1,
            }
        else:
            grouped[key]["count"] += 1

    equipped_lines = []
    carried_lines = []

    for (name, item_type, effect, is_equipped, slot), data in grouped.items():
        count = data["count"]
        item = data["item"]
        icon = get_item_icon(name, item_type, effect, slot if is_equipped else "")
        count_str = f" **(x{count})**" if count > 1 else ""
        if effect.startswith("[GEAR_JSON]") or effect.startswith("[ITEM_JSON]"):
            from mechanics.combat.equipment import parse_equipment_metadata
            meta = parse_equipment_metadata(item)
            stats = meta.get("stat_modifiers", {})
            social_mods = meta.get("social_modifiers", {})
            stat_parts = []
            if "atk" in stats: stat_parts.append(f"⚔️ ATK +{stats['atk']}")
            if "matk" in stats: stat_parts.append(f"🔮 MATK +{stats['matk']}")
            if "def" in stats: stat_parts.append(f"🛡️ DEF +{stats['def']}")
            if "mdef" in stats: stat_parts.append(f"✨ MDEF +{stats['mdef']}")
            if "block_chance" in meta and meta.get("block_chance", 0) > 0: stat_parts.append(f"🛡️ Block {meta['block_chance']}%")
            for sk, sv in social_mods.items():
                if sv > 0: stat_parts.append(f"{sk.upper()} +{sv}")
            effect_str = f"\n└ *{' • '.join(stat_parts)}*" if stat_parts else ""
        elif effect.startswith("[SPELLBOOK_JSON]"):
            from mechanics.combat.equipment import parse_equipment_metadata
            from mechanics.combat.spells import get_spell
            meta_spell = parse_equipment_metadata(item)
            sp = get_spell(meta_spell.get("spell_id")) if meta_spell.get("spell_id") else meta_spell.get("spell_data")
            if sp:
                tt = sp.get("target_type", "single").upper()
                crit_b = sp.get("crit_bonus", 0.0)
                scope_tag = "Chain" if tt == "CHAIN" else ("AOE" if tt == "AOE" else (f"+{int(crit_b*100)}% Crit" if crit_b >= 0.12 else "ST"))
                effect_str = f"\n└ *{sp.get('school', 'Magic')} • {sp.get('mp_cost', 0)} MP • {scope_tag}*"
            else:
                effect_str = f"\n└ *Teaches {meta_spell.get('spell_name', 'Spell')}*"
        elif effect.startswith("[DIGITAL_JSON]"):
            from mechanics.combat.items import parse_digital_item_metadata
            d_meta = parse_digital_item_metadata(item) or {}
            cap = d_meta.get("caption", "")[:80]
            effect_str = f"\n└ *\"{cap}\"* [📱 Digital Media]" if cap else "\n└ *[📱 Digital Media]*"
        elif effect.startswith("[CONSUMABLE_JSON]"):
            from mechanics.combat.items.consumables import parse_consumable_metadata
            c_meta = parse_consumable_metadata(item) or {}
            desc = c_meta.get("effect_desc") or c_meta.get("description") or ""
            if not desc:
                parts = []
                if c_meta.get("hp_restore"): parts.append(f"❤️ +{c_meta['hp_restore']} HP")
                if c_meta.get("mp_restore"): parts.append(f"✨ +{c_meta['mp_restore']} MP")
                desc = " • ".join(parts)
            effect_str = f"\n└ *{desc}*" if desc else ""
        elif effect:
            clean_effect = effect.replace("(flavor only -- confers no stat bonus)", "").replace("Starting weapon (flavor only -- confers no stat bonus).", "").strip()
            effect_str = f"\n└ *{clean_effect}*" if clean_effect else ""
        else:
            effect_str = ""

        if is_equipped and slot:
            slot_emoji = EQUIPMENT_SLOT_EMOJI.get(slot, "🛡️")
            equipped_lines.append(f"{slot_emoji} **{slot}:** {icon} **{name}**{count_str}{effect_str}")
        else:
            total_cost = item.get("slot_cost", 1) * count
            from mechanics.combat.items import is_digital_item
            if is_digital_item(item) or total_cost == 0:
                cost_str = " `[Digital]`"
            else:
                cost_str = f" [{total_cost} slot{'s' if total_cost > 1 else ''}]" if total_cost > 0 else ""
            carried_lines.append(f"{icon} **{name}**{count_str} `{item_type}`{cost_str}{effect_str}")

    def _add_section(section_title: str, lines: list[str]):
        if not lines:
            return
        current_chunk = []
        current_len = 0
        field_index = 1

        for line in lines:
            line_len = len(line) + 1
            if current_len + line_len > 1000:
                if len(embed.fields) >= 24:
                    embed.add_field(name=f"{section_title} (cont.)", value="...and more items.", inline=False)
                    return
                title = section_title if field_index == 1 else f"{section_title} ({field_index})"
                embed.add_field(name=title, value="\n".join(current_chunk), inline=False)
                current_chunk = [line]
                current_len = line_len
                field_index += 1
            else:
                current_chunk.append(line)
                current_len += line_len

        if current_chunk and len(embed.fields) < 25:
            title = section_title if field_index == 1 else f"{section_title} ({field_index})"
            embed.add_field(name=title, value="\n".join(current_chunk), inline=False)

    _add_section("🛡️ Equipped Gear", equipped_lines)
    _add_section("🎒 Carried Items", carried_lines)

    embed.set_footer(text="Manage your gear, potions, and items in real-time below.")
    return embed


# ==============================================================================
# UI COMPONENTS & MODALS FOR INVENTORY DASHBOARD
# ==============================================================================

class InventoryDashboardView(discord.ui.View):
    """Main interactive hub view for /inventory."""
    def __init__(self, user_id: int, feedback: str = ""):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.feedback = feedback

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This is not your inventory dashboard.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Equip", style=discord.ButtonStyle.primary, emoji="⚔️", row=0)
    async def equip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        inv = await adb(db.get_inventory, self.user_id)
        carried = [i for i in inv if not i.get("equipped")]
        if not carried:
            await interaction.response.send_message("❌ You have no carried items to equip.", ephemeral=True)
            return

        view = EquipItemSelectView(self.user_id, carried)
        await interaction.response.send_message("⚔️ Select an item to equip:", view=view, ephemeral=True)

    @discord.ui.button(label="Unequip", style=discord.ButtonStyle.secondary, emoji="🛡️", row=0)
    async def unequip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        inv = await adb(db.get_inventory, self.user_id)
        equipped = [i for i in inv if i.get("equipped") and i.get("slot")]
        if not equipped:
            await interaction.response.send_message("❌ You have no gear currently equipped.", ephemeral=True)
            return

        view = UnequipSlotSelectView(self.user_id, equipped)
        await interaction.response.send_message("🛡️ Select a slot to unequip:", view=view, ephemeral=True)

    @discord.ui.button(label="Use Item", style=discord.ButtonStyle.success, emoji="🧪", row=0)
    async def use_item_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        inv = await adb(db.get_inventory, self.user_id)
        usable = [i for i in inv if not i.get("equipped")]
        if not usable:
            await interaction.response.send_message("❌ You have no usable items in your inventory.", ephemeral=True)
            return

        view = UseItemSelectView(self.user_id, usable)
        await interaction.response.send_message("🧪 Select an item to use:", view=view, ephemeral=True)

    @discord.ui.button(label="Drop", style=discord.ButtonStyle.danger, emoji="🗑️", row=1)
    async def drop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        from mechanics.combat.items import is_key_item
        inv = await adb(db.get_inventory, self.user_id)
        carried = [i for i in inv if not i.get("equipped") and not is_key_item(i)]
        if not carried:
            await interaction.response.send_message("❌ You have no droppable items in your inventory (Key Items & Narrative Artifacts cannot be discarded).", ephemeral=True)
            return

        view = DropItemSelectView(self.user_id, carried)
        await interaction.response.send_message("🗑️ Select an item to drop:", view=view, ephemeral=True)

    @discord.ui.button(label="Inspect", style=discord.ButtonStyle.secondary, emoji="🔍", row=1)
    async def inspect_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        inv = await adb(db.get_inventory, self.user_id)
        if not inv:
            await interaction.response.send_message("❌ Your inventory is empty.", ephemeral=True)
            return

        view = InspectItemSelectView(self.user_id, inv)
        await interaction.response.send_message("🔍 Select an item to inspect:", view=view, ephemeral=True)


# ------------------------------------------------------------------------------
# 1. EQUIP FLOW
# ------------------------------------------------------------------------------

class EquipItemSelectDropdown(discord.ui.Select):
    def __init__(self, user_id: int, items: list[dict]):
        self.user_id = user_id
        options = []
        seen = set()
        for item in items[:25]:
            name = item["name"]
            if name in seen:
                continue
            seen.add(name)
            icon = get_item_icon(name, item.get("item_type", ""), item.get("effect", ""))
            default_slot = DEFAULT_EQUIP_SLOT_FOR_ITEM_TYPE.get(item.get("item_type", ""), "Weapon")
            options.append(discord.SelectOption(
                label=f"{name}"[:100],
                value=str(item["id"]),
                description=f"Type: {item.get('item_type', 'Gear')} | Auto-Slot: {default_slot}"[:100],
                emoji=icon
            ))
        super().__init__(placeholder="Choose an item to equip...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        item_id = int(self.values[0])
        inv = await adb(db.get_inventory, self.user_id)
        match = next((i for i in inv if i["id"] == item_id), None)
        if not match:
            await interaction.response.send_message("❌ Item no longer found in inventory.", ephemeral=True)
            return

        # Open slot picker
        view = EquipSlotSelectView(self.user_id, match)
        await interaction.response.edit_message(
            content=f"⚔️ Equip **{match['name']}** into which gear slot?",
            view=view
        )


class EquipItemSelectView(discord.ui.View):
    def __init__(self, user_id: int, items: list[dict]):
        super().__init__(timeout=120)
        self.add_item(EquipItemSelectDropdown(user_id, items))


class EquipSlotSelectDropdown(discord.ui.Select):
    def __init__(self, user_id: int, item: dict):
        self.user_id = user_id
        self.item = item

        char = db.get_character(user_id)
        session_id = db.get_active_session_id_for_user(user_id)
        session = db.get_session(session_id) if session_id else {}
        scenario = session.get("scenario", char.get("scenario", "fantasy") if char else "fantasy")
        from scenario_data import is_non_combat_scenario
        is_non_combat = is_non_combat_scenario(scenario)

        from mechanics.combat.equipment import is_two_handed
        item_is_2h = is_two_handed(item)

        inv = db.get_inventory(user_id)
        current_weapon = next((i for i in inv if i.get("equipped") and i.get("slot") == "Weapon"), None)
        current_shield = next((i for i in inv if i.get("equipped") and i.get("slot") == "Shield"), None)
        weapon_is_2h = bool(current_weapon and is_two_handed(current_weapon))

        default_slot = DEFAULT_EQUIP_SLOT_FOR_ITEM_TYPE.get(item.get("item_type", ""), "Weapon")

        from mechanics.combat.equipment import parse_equipment_metadata
        item_meta = parse_equipment_metadata(item) or {}
        item_type = str(item.get("item_type") or item_meta.get("item_type") or "").strip().title()
        archetype = str(item_meta.get("archetype") or "").strip().lower()

        # Slot filtering
        is_combat_armor = (item_type == "Armor") or (item_meta.get("base_dt", 0) > 2 and archetype not in ("cloth_hood", "cap", "tech_visor", "open_helm", "full_greathelm"))
        is_clothing = (item_type == "Clothing") or (archetype in ("casual_shirt", "blouse", "school_uniform_top", "jacket", "hoodie", "robe", "tunic", "trousers", "skirt", "shorts", "slacks", "jeans"))
        is_headwear = (item_type in ("Headwear", "Helmet", "Head")) or (archetype in ("cloth_hood", "cap", "open_helm", "full_greathelm", "tech_visor", "gas_mask", "circlet", "formal_hat"))
        is_shield = (item_type == "Shield") or (archetype in ("buckler", "heater_shield", "tower_shield", "riot_shield", "energy_shield"))
        is_weapon = (item_type == "Weapon") or ("multiplier" in item_meta) or (archetype in ("dagger", "shortsword", "wand", "pistol", "throwing", "sword", "axe", "mace", "spear", "revolver", "greatsword", "polearm", "warhammer", "staff", "bow", "crossbow", "rifle", "shotgun", "machinegun", "explosive", "katana"))

        valid_slots = None
        if is_combat_armor:
            valid_slots = ["Armor"]
        elif is_clothing:
            valid_slots = ["Top", "Bottom"]
        elif is_headwear:
            valid_slots = ["Head"]
        elif is_shield:
            valid_slots = ["Shield"]
        elif is_weapon:
            valid_slots = ["Weapon", "Shield"]
        elif item_type == "Accessory":
            valid_slots = ["Accessory 1", "Accessory 2", "Accessory 3", "Accessory 4"]

        options = []
        for slot in EQUIPMENT_SLOTS:
            if valid_slots and slot not in valid_slots:
                continue
            if is_non_combat:
                from mechanics.combat.items import can_equip_item_in_scenario
                allowed, _ = can_equip_item_in_scenario(item, slot, scenario)
                if not allowed:
                    continue
            # 2-Handed weapons cannot be equipped in Shield / off-hand slot
            if item_is_2h and slot == "Shield":
                continue

            emoji = EQUIPMENT_SLOT_EMOJI.get(slot, "🛡️")
            is_default = (slot == default_slot)
            
            if slot == "Weapon" and item_is_2h and current_shield:
                desc = "⚠️ Will unequip off-hand shield (requires two hands)"
            elif slot == "Shield" and weapon_is_2h:
                desc = "⚠️ Will unequip two-handed weapon"
            elif slot == "Shield" and is_weapon and not item_is_2h:
                desc = "🗡️ Equip as Off-Hand Weapon (Dual-Wielding)"
                emoji = "🗡️"
            elif is_default:
                desc = "⭐ Recommended slot for this item"
            else:
                desc = f"Equip to {slot} slot"

            options.append(discord.SelectOption(
                label=f"{slot}",
                value=slot,
                description=desc[:100],
                emoji=emoji,
                default=is_default
            ))
        super().__init__(placeholder="Choose slot...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        slot = self.values[0]
        
        char = await adb(db.get_character, self.user_id)
        session_id = await adb(db.get_active_session_id_for_user, self.user_id)
        session = (await adb(db.get_session, session_id)) if session_id else {}
        scenario = session.get("scenario", char.get("scenario", "fantasy") if char else "fantasy")
        from mechanics.combat.items import can_equip_item_in_scenario
        allowed, reason = can_equip_item_in_scenario(self.item, slot, scenario)
        if not allowed:
            await interaction.response.send_message(reason, ephemeral=True)
            return

        inv = await adb(db.get_inventory, self.user_id)
        from mechanics.combat.equipment import is_two_handed
        mutual_unequipped = None
        if slot == "Weapon" and is_two_handed(self.item):
            mutual_unequipped = next((i for i in inv if i.get("equipped") and i.get("slot") == "Shield"), None)
        elif slot == "Shield":
            equipped_w = next((i for i in inv if i.get("equipped") and i.get("slot") == "Weapon"), None)
            if equipped_w and is_two_handed(equipped_w):
                mutual_unequipped = equipped_w

        try:
            previous = await adb(db.equip_item, self.user_id, self.item["id"], slot)
        except ValueError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return

        icon = get_item_icon(self.item["name"], self.item.get("item_type", ""), self.item.get("effect", ""), slot)
        notice = f"✨ Equipped {icon} **{self.item['name']}** in **{slot}**!"
        if previous:
            prev_icon = get_item_icon(previous["name"], previous.get("item_type", ""), previous.get("effect", ""), "")
            notice += f" *(Returned {prev_icon} {previous['name']} to bag)*"
        if mutual_unequipped:
            mut_icon = get_item_icon(mutual_unequipped["name"], mutual_unequipped.get("item_type", ""), mutual_unequipped.get("effect", ""), "")
            notice += f"\n*(Returned {mut_icon} **{mutual_unequipped['name']}** to bag: two-handed weapon requires both hands)*"

        embed = build_inventory_embed(self.user_id, feedback_notice=notice)
        await interaction.response.edit_message(content=notice, view=None)


class EquipSlotSelectView(discord.ui.View):
    def __init__(self, user_id: int, item: dict):
        super().__init__(timeout=120)
        self.add_item(EquipSlotSelectDropdown(user_id, item))


# ------------------------------------------------------------------------------
# 2. UNEQUIP FLOW
# ------------------------------------------------------------------------------

class UnequipSlotSelectDropdown(discord.ui.Select):
    def __init__(self, user_id: int, equipped_items: list[dict]):
        self.user_id = user_id
        options = []
        for item in equipped_items[:25]:
            slot = item.get("slot", "Weapon")
            emoji = EQUIPMENT_SLOT_EMOJI.get(slot, "🛡️")
            options.append(discord.SelectOption(
                label=f"{slot}: {item['name']}"[:100],
                value=slot,
                description=f"Unequip {item['name']} back into carried bag"[:100],
                emoji=emoji
            ))
        super().__init__(placeholder="Choose slot to unequip...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        slot = self.values[0]
        removed = await adb(db.unequip_slot, self.user_id, slot)
        if not removed:
            await interaction.response.send_message(f"❌ Your **{slot}** slot is already empty.", ephemeral=True)
            return

        icon = get_item_icon(removed["name"], removed.get("item_type", ""), removed.get("effect", ""), "")
        notice = f"🛡️ Unequipped {icon} **{removed['name']}** from **{slot}**."
        await interaction.response.edit_message(content=notice, view=None)


class UnequipSlotSelectView(discord.ui.View):
    def __init__(self, user_id: int, equipped_items: list[dict]):
        super().__init__(timeout=120)
        self.add_item(UnequipSlotSelectDropdown(user_id, equipped_items))


# ------------------------------------------------------------------------------
# 3. USE / CONSUME ITEM FLOW (OUT-OF-COMBAT)
# ------------------------------------------------------------------------------

class UseItemSelectDropdown(discord.ui.Select):
    def __init__(self, user_id: int, items: list[dict]):
        self.user_id = user_id
        options = []
        seen = set()
        for item in items[:25]:
            name = item["name"]
            if name in seen:
                continue
            seen.add(name)
            parsed = parse_item_effect(item)
            icon = get_item_icon(name, item.get("item_type", ""), item.get("effect", ""))
            desc = item.get("effect") or f"Category: {parsed['category'].capitalize()}"
            options.append(discord.SelectOption(
                label=f"{name}"[:100],
                value=str(item["id"]),
                description=desc[:100],
                emoji=icon
            ))
        super().__init__(placeholder="Choose item to consume/use...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        item_id = int(self.values[0])
        inv = await adb(db.get_inventory, self.user_id)
        match = next((i for i in inv if i["id"] == item_id), None)
        if not match:
            await interaction.response.send_message("❌ Item not found.", ephemeral=True)
            return

        session_id = await adb(db.get_active_session_id_for_user, self.user_id)
        session = (await adb(db.get_session, session_id)) if session_id else None

        from mechanics.combat.items import is_digital_item
        if is_digital_item(match):
            ok, msg = apply_item_to_target(self.user_id, match, target_type="self", target_name="Yourself", session=session)
            await interaction.response.edit_message(content=msg, view=None)
            return

        # Build target choices: Self + Companions + Other party members
        targets = [{"label": "🧑 Yourself (Self)", "type": "self", "name": "Yourself", "user_id": self.user_id}]

        if session:
            # Active companions
            for npc in (session.get("current_npcs") or []):
                if isinstance(npc, dict) and npc.get("hp") is not None:
                    targets.append({
                        "label": f"⭐ {npc.get('name', 'Companion')} (❤️ {npc.get('hp', 0)}/{npc.get('max_hp', 40)})",
                        "type": "companion",
                        "name": npc.get("name", "Companion"),
                        "user_id": None
                    })
            # Other party players
            for uid in session.get("turn_order", []):
                if uid != self.user_id:
                    p_char = await adb(db.get_character, uid)
                    if p_char:
                        targets.append({
                            "label": f"🛡️ {p_char['name']} (❤️ {p_char['hp']}/{p_char['max_hp']})",
                            "type": "player",
                            "name": p_char["name"],
                            "user_id": uid
                        })

            # Contacts & NPCs (for Gifting)
            from mechanics.combat.items import is_giftable_item
            if is_giftable_item(match):
                char = (await adb(db.get_character, self.user_id)) or {}
                char_id = char.get("id", 0)
                contacts = await adb(db.get_contacts, session["id"], character_id=char_id)
                seen_names = {t["name"].lower() for t in targets}
                for c in contacts:
                    c_name = c.get("name")
                    if c_name and c_name.lower() not in seen_names:
                        seen_names.add(c_name.lower())
                        score = c.get("relationship_score", 0)
                        targets.append({
                            "label": f"👤 {c_name} (Contact: {score:+d} pts)",
                            "type": "contact",
                            "name": c_name,
                            "user_id": None
                        })

        if len(targets) == 1:
            # Only self available -> execute directly
            ok, msg = apply_item_to_target(self.user_id, match, target_type="self", target_name="Yourself", session=session)
            await interaction.response.edit_message(content=msg, view=None)
        else:
            # Open Target Selector
            view = UseItemTargetSelectView(self.user_id, match, targets, session)
            await interaction.response.edit_message(
                content=f"🎯 Choose who to use **{match['name']}** on:",
                view=view
            )


class UseItemSelectView(discord.ui.View):
    def __init__(self, user_id: int, items: list[dict]):
        super().__init__(timeout=120)
        self.add_item(UseItemSelectDropdown(user_id, items))


class UseItemTargetSelectDropdown(discord.ui.Select):
    def __init__(self, user_id: int, item: dict, targets: list[dict], session: dict = None):
        self.user_id = user_id
        self.item = item
        self.targets = targets
        self.session = session

        options = []
        for idx, t in enumerate(targets[:25]):
            options.append(discord.SelectOption(
                label=t["label"][:100],
                value=str(idx),
                description=f"Apply {item['name']} to this target"[:100]
            ))
        super().__init__(placeholder="Select recipient...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        idx = int(self.values[0])
        target = self.targets[idx]
        ok, msg = apply_item_to_target(
            self.user_id,
            self.item,
            target_type=target["type"],
            target_name=target["name"],
            session=self.session,
            target_user_id=target["user_id"]
        )
        await interaction.response.edit_message(content=msg, view=None)


class UseItemTargetSelectView(discord.ui.View):
    def __init__(self, user_id: int, item: dict, targets: list[dict], session: dict = None):
        super().__init__(timeout=120)
        self.add_item(UseItemTargetSelectDropdown(user_id, item, targets, session))


# ------------------------------------------------------------------------------
# 4. DROP ITEM FLOW
# ------------------------------------------------------------------------------

class DropItemSelectDropdown(discord.ui.Select):
    def __init__(self, user_id: int, items: list[dict]):
        self.user_id = user_id
        options = []
        seen = set()
        for item in items[:25]:
            name = item["name"]
            if name in seen:
                continue
            seen.add(name)
            icon = get_item_icon(name, item.get("item_type", ""), item.get("effect", ""))
            options.append(discord.SelectOption(
                label=f"{name}"[:100],
                value=name,
                description=f"Type: {item.get('item_type', 'Item')} | Cost: {item.get('slot_cost', 1)} slot"[:100],
                emoji=icon
            ))
        super().__init__(placeholder="Choose an item to discard...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        from mechanics.combat.items import is_key_item
        item_name = self.values[0]
        inv = await adb(db.get_inventory, self.user_id)
        match = next((i for i in inv if i.get("name") == item_name), None)
        if match and is_key_item(match):
            await interaction.response.edit_message(content=f"🚫 **{item_name}** is a Key Item or Narrative Artifact and cannot be discarded!", view=None)
            return

        removed = await adb(db.remove_item_by_name, self.user_id, item_name)
        if removed:
            await interaction.response.edit_message(content=f"🗑️ Discarded **{item_name}** from your inventory.", view=None)
        else:
            await interaction.response.edit_message(content=f"❌ Could not find **{item_name}** to discard.", view=None)


class DropItemSelectView(discord.ui.View):
    def __init__(self, user_id: int, items: list[dict]):
        super().__init__(timeout=120)
        self.add_item(DropItemSelectDropdown(user_id, items))


# ------------------------------------------------------------------------------
# 5. INSPECT ITEM FLOW
# ------------------------------------------------------------------------------

def build_item_inspect_embed(item: dict, user_id: int) -> discord.Embed:
    """Builds a rich inspect embed displaying equipment stats card, category, and lore."""
    from mechanics.combat.items import is_digital_item, parse_digital_item_metadata, is_key_item
    icon = get_item_icon(item["name"], item.get("item_type", ""), item.get("effect", ""), item.get("slot", ""))
    parsed = parse_item_effect(item)
    effect_raw = str(item.get("effect", "") or "")

    # Check Key Items / Narrative Artifacts
    if is_key_item(item):
        clean_desc = effect_raw.replace("Important narrative item:", "").strip()
        lore_text = clean_desc if clean_desc else f"An indispensable artifact tied to your journey: **{item['name']}**."
        embed = discord.Embed(
            title=f"{icon} {item['name']}",
            color=discord.Color.purple()
        )
        embed.add_field(name="Category / Classification", value="`Key Item` (Narrative Artifact)", inline=True)
        embed.add_field(name="Inventory Weight", value="`0 slots` (Weightless)", inline=True)
        embed.add_field(name="Protection Status", value="🔒 **Protected (Undroppable)**", inline=True)
        embed.add_field(
            name="📜 Narrative Record & Significance",
            value=f"> *\"{lore_text}\"*",
            inline=False
        )
        embed.set_footer(text="Key items cannot be discarded or sold. Present them during dialogue or actions when required.")
        return embed

    # Check Digital Media Collectible
    if is_digital_item(item):
        d_meta = parse_digital_item_metadata(item) or {}
        caption = d_meta.get("caption") or effect_raw
        contact_name = d_meta.get("contact_name", "Unknown Contact")
        media_type = d_meta.get("media_type", "photo")
        tags = d_meta.get("tags", ["misc", "digital"])
        tag_str = " ".join(f"`#{t}`" for t in tags)

        if "video" in media_type and ("nsfw" in media_type or "intimate" in media_type):
            type_title = "🔞 Intimate Video"
            color = discord.Color.red()
        elif "video" in media_type:
            type_title = "📹 Video Clip"
            color = discord.Color.blue()
        elif "nsfw" in media_type or "intimate" in media_type:
            type_title = "🔞 Intimate Photo"
            color = discord.Color.magenta()
        else:
            type_title = "📸 Digital Photo"
            color = discord.Color.teal()

        embed = discord.Embed(
            title=f"{icon} {item['name']}",
            color=color
        )
        embed.add_field(name="Category / Type", value="`Misc` (Digital Media)", inline=True)
        embed.add_field(name="Inventory Weight", value="`0 slots` (Device Storage)", inline=True)
        embed.add_field(name="Tags", value=tag_str, inline=True)
        embed.add_field(name="Sender / Subject", value=f"**{contact_name}**", inline=True)
        embed.add_field(name="Media Type", value=f"**{type_title}**", inline=True)
        embed.add_field(name="Format", value="Encrypted Digital Asset 📱", inline=True)
        embed.add_field(
            name="🖼️ Visual Description / Transcript",
            value=f"> *\"{caption}\"*",
            inline=False
        )
        embed.set_footer(text="Digital media is stored on your device. It is never consumed on use. Discard via 'Drop' if needed.")
        return embed

    # Check Spellbooks / Grimoires
    is_spellbook = (
        item.get("item_type") == "Spellbook"
        or effect_raw.startswith("[SPELLBOOK_JSON]")
        or any(item.get("name", "").lower().startswith(p) for p in ["spellbook:", "grimoire:", "tome:", "scroll:"])
    )
    if is_spellbook:
        spell_id = None
        if effect_raw.startswith("[SPELLBOOK_JSON]"):
            from mechanics.combat.equipment import parse_equipment_metadata
            meta = parse_equipment_metadata(item)
            spell_id = meta.get("spell_id")
        elif any(item.get("name", "").lower().startswith(p) for p in ["spellbook:", "grimoire:", "tome:", "scroll:"]):
            parts = item["name"].split(":", 1)
            if len(parts) > 1:
                sp_name = parts[1].strip()
                from mechanics.combat.spells import get_all_spells
                for sid, sp in get_all_spells().items():
                    if sp["name"].lower() == sp_name.lower():
                        spell_id = sid
                        break

        from mechanics.combat.spells import get_spell
        sp = get_spell(spell_id) if spell_id else None
        if sp:
            tier_str = sp.get("tier_name", "Basic")
            disc_str = sp.get("discipline", "attack").title()
            mp_cost = sp.get("mp_cost", 0)
            char = db.get_character(user_id) if user_id else None
            max_mp = char.get("max_mp", 0) if char else 0

            embed = discord.Embed(
                title=f"{icon} {item['name']}",
                color=discord.Color.blue()
            )
            embed.add_field(name="Category / Type", value="`Spellbook` (Arcane Grimoire)", inline=True)
            embed.add_field(name="Inventory Weight", value=f"{item.get('slot_cost', 1)} slot(s)", inline=True)
            embed.add_field(name="Spell Contained", value=f"{sp.get('emoji', '🔮')} **{sp['name']}**", inline=True)
            embed.add_field(name="School / Discipline", value=f"{sp.get('school', 'Magic')} ({disc_str})", inline=True)
            embed.add_field(name="Tier / Damage Type", value=f"{tier_str} | {sp.get('damage_type', 'Magical').title()}", inline=True)
            embed.add_field(name="MP Casting Cost", value=f"💙 **{mp_cost} MP**", inline=True)

            if max_mp < mp_cost:
                embed.add_field(
                    name="⚠️ Arcane Compatibility",
                    value=f"**Insufficient MP Capacity!**\nRequires **{mp_cost} MP**, but your max MP is **{max_mp} MP**.\n*(You can study this grimoire now, but you must raise your INT/Arcane pool before you can cast it in combat).* ",
                    inline=False
                )
            else:
                embed.add_field(
                    name="✨ Arcane Compatibility",
                    value=f"**Fully Compatible!**\nYour max MP (**{max_mp} MP**) is sufficient to channel this spell.",
                    inline=False
                )

            desc = sp.get("description", "")
            if desc:
                embed.add_field(name="📜 Arcane Inscription", value=f"> *\"{desc}\"*", inline=False)
            embed.set_footer(text="Use this spellbook from your inventory to study and permanently master this spell.")
            return embed

    embed = discord.Embed(
        title=f"{icon} {item['name']}",
        color=discord.Color.gold()
    )
    embed.add_field(name="Category / Type", value=f"`{item.get('item_type', 'Item')}` ({parsed['category'].capitalize()})", inline=True)
    embed.add_field(name="Inventory Weight", value=f"{item.get('slot_cost', 1)} slot(s)", inline=True)

    if item.get("equipped") and item.get("slot"):
        embed.add_field(name="Equipped Status", value=f"Equipped in **{item['slot']}**", inline=True)

    char = db.get_character(user_id)
    char_scen = char.get("scenario", "fantasy") if char else "fantasy"
    from scenario_data import is_non_combat_scenario
    is_non_combat = is_non_combat_scenario(char_scen)

    effect_raw = str(item.get("effect", "") or "")

    from mechanics.combat.equipment import parse_equipment_metadata
    from mechanics.combat.items import format_equipment_card
    item_type = item.get("item_type", "")
    slot = item.get("slot") or ""

    is_equipment = (
        item_type in ("Weapon", "Armor", "Clothing", "Shield", "Accessory")
        or bool(slot)
        or effect_raw.startswith("[GEAR_JSON]")
        or effect_raw.startswith("[ITEM_JSON]")
    )

    if is_non_combat and is_equipment:
        embed.description = "🎭 **Cosmetic / Narrative Gear**\n*In this non-combat scenario, equipment serves cosmetic & narrative roles without combat stats.*"
        clean_effect = effect_raw.replace("(flavor only -- confers no stat bonus)", "").replace("Starting weapon (flavor only -- confers no stat bonus).", "").strip()
        if clean_effect and not clean_effect.startswith("[GEAR_JSON]") and not clean_effect.startswith("[SPELLBOOK_JSON]"):
            embed.add_field(name="📜 Description", value=clean_effect, inline=False)
    elif is_equipment:
        meta = parse_equipment_metadata(item)
        if meta and (meta.get("archetype") or meta.get("stat_modifiers") or meta.get("social_modifiers") or meta.get("damage_types")):
            embed.description = format_equipment_card(meta)
        clean_effect = effect_raw.replace("(flavor only -- confers no stat bonus)", "").replace("Starting weapon (flavor only -- confers no stat bonus).", "").strip()
        if clean_effect and not clean_effect.startswith("[GEAR_JSON]") and not clean_effect.startswith("[SPELLBOOK_JSON]"):
            embed.add_field(name="📜 Lore / Description", value=clean_effect, inline=False)

        # Auto-Compare with Equipped Gear in Target Slot
        if not item.get("equipped") and not is_non_combat:
            target_slot = slot or DEFAULT_EQUIP_SLOT_FOR_ITEM_TYPE.get(item_type, "Weapon")
            equipped_dict = db.get_equipment(user_id) if user_id else {}
            
            # For accessories, compare against Accessory 1 or the first equipped accessory
            if target_slot.startswith("Accessory"):
                cur_equipped = equipped_dict.get(target_slot)
                if not cur_equipped:
                    for acc_k in ("Accessory 1", "Accessory 2", "Accessory 3", "Accessory 4"):
                        if equipped_dict.get(acc_k):
                            cur_equipped = equipped_dict[acc_k]
                            target_slot = acc_k
                            break
            else:
                cur_equipped = equipped_dict.get(target_slot)

            if not cur_equipped:
                embed.add_field(
                    name=f"🔄 vs Equipped ({target_slot})",
                    value=f"*Slot is currently empty.* ✨ **Free upgrade!** Equipping this will grant all stats with no trade-offs.",
                    inline=False
                )
            else:
                cur_meta = parse_equipment_metadata(cur_equipped) or {}
                cur_name = cur_equipped.get("name", "Equipped Item")
                diff_lines = []

                def _fmt_delta(cur_v, new_v, is_pct=False, higher_is_better=True):
                    delta = round(new_v - cur_v, 2)
                    unit = "%" if is_pct else ""
                    if delta > 0:
                        icon = "🔺" if higher_is_better else "🔻"
                        return f"`{cur_v}{unit}` ➔ `{new_v}{unit}` (+{delta}{unit} {icon})"
                    elif delta < 0:
                        icon = "🔻" if higher_is_better else "🔺"
                        return f"`{cur_v}{unit}` ➔ `{new_v}{unit}` ({delta}{unit} {icon})"
                    else:
                        return f"`{cur_v}{unit}` ➔ `{new_v}{unit}` (➖)"

                # Weapon Comparisons
                if target_slot == "Weapon" or item_type == "Weapon":
                    c_mult = float(cur_meta.get("multiplier", 1.0))
                    n_mult = float(meta.get("multiplier", 1.0))
                    if c_mult != n_mult:
                        diff_lines.append(f"• **Power Mult:** {_fmt_delta(c_mult, n_mult)}")

                    c_crit = float(cur_meta.get("crit_bonus", 0.0))
                    n_crit = float(meta.get("crit_bonus", 0.0))
                    if c_crit != n_crit:
                        diff_lines.append(f"• **Crit Bonus:** {_fmt_delta(c_crit, n_crit, is_pct=True)}")

                    c_ap = float(cur_meta.get("armor_penetration", cur_meta.get("armor_piercing", 0.0)))
                    n_ap = float(meta.get("armor_penetration", meta.get("armor_piercing", 0.0)))
                    if c_ap > 0 or n_ap > 0:
                        diff_lines.append(f"• **Armor Piercing:** {_fmt_delta(int(c_ap * 100), int(n_ap * 100), is_pct=True)}")

                    c_acc = int(cur_meta.get("stat_modifiers", {}).get("acc", 0))
                    n_acc = int(meta.get("stat_modifiers", {}).get("acc", 0))
                    if c_acc != n_acc:
                        diff_lines.append(f"• **Accuracy:** {_fmt_delta(c_acc, n_acc, is_pct=True)}")

                # Armor / Head / Shield Comparisons
                c_dt = int(cur_meta.get("base_dt", cur_meta.get("dt_contribution", 0)))
                n_dt = int(meta.get("base_dt", meta.get("dt_contribution", 0)))
                if c_dt > 0 or n_dt > 0 or target_slot in ("Armor", "Shield", "Head"):
                    if c_dt != n_dt:
                        diff_lines.append(f"• **Base DT:** {_fmt_delta(c_dt, n_dt)}")

                c_blk = int(cur_meta.get("block_chance", 0))
                n_blk = int(meta.get("block_chance", 0))
                if c_blk > 0 or n_blk > 0 or target_slot == "Shield":
                    if c_blk != n_blk:
                        diff_lines.append(f"• **Block Chance:** {_fmt_delta(c_blk, n_blk, is_pct=True)}")

                c_eva = int(cur_meta.get("base_eva", cur_meta.get("stat_modifiers", {}).get("eva", 0)))
                n_eva = int(meta.get("base_eva", meta.get("stat_modifiers", {}).get("eva", 0)))
                if c_eva != n_eva:
                    diff_lines.append(f"• **EVA Mod:** {_fmt_delta(c_eva, n_eva, is_pct=True)}")

                # Stat Modifiers / Social Modifiers
                c_mods = dict(cur_meta.get("stat_modifiers") or {})
                for sk, sv in (cur_meta.get("social_modifiers") or {}).items():
                    c_mods[sk] = c_mods.get(sk, 0) + sv
                n_mods = dict(meta.get("stat_modifiers") or {})
                for sk, sv in (meta.get("social_modifiers") or {}).items():
                    n_mods[sk] = n_mods.get(sk, 0) + sv

                all_stat_keys = sorted(set(c_mods.keys()) | set(n_mods.keys()))
                for sk in all_stat_keys:
                    if sk in ("base_dt", "dt_bonus", "eva", "acc", "multiplier", "crit_bonus", "armor_penetration"):
                        continue
                    cv = c_mods.get(sk, 0)
                    nv = n_mods.get(sk, 0)
                    if cv != nv and isinstance(cv, (int, float)) and isinstance(nv, (int, float)):
                        diff_lines.append(f"• **{sk.upper()}:** {_fmt_delta(cv, nv)}")

                if not diff_lines:
                    diff_lines.append("• *Identical combat stat profile.*")

                embed.add_field(
                    name=f"🔄 vs Equipped in {target_slot} ({cur_name})",
                    value="\n".join(diff_lines[:8]),
                    inline=False
                )
    elif effect_raw.startswith("[SPELLBOOK_JSON]"):
        from mechanics.combat.spells import get_spell
        meta_spell = parse_equipment_metadata(item)
        sp_id = meta_spell.get("spell_id")
        sp = get_spell(sp_id) if sp_id else meta_spell.get("spell_data")
        if sp:
            tt = sp.get("target_type", "single").title()
            acc_m = sp.get("acc_mod", 0)
            acc_str = f"+{acc_m}%" if acc_m > 0 else (f"{acc_m}%" if acc_m < 0 else "Base")
            crit_b = sp.get("crit_bonus", 0.0)
            crit_str = f" • +{int(crit_b*100)}% Crit" if crit_b > 0 else ""
            power = sp.get("power_mult", 1.0)
            elem = sp.get("damage_type", "magical").title()
            extra_notes = ""
            if sp.get("target_type") == "chain":
                extra_notes = f"\n⚡ *Bounces to {sp.get('max_bounces', 3)} foes with 25% damage decay per bounce.*"
            elif sp.get("target_type") == "aoe":
                extra_notes = "\n🌊 *Hits all enemies. Glancing Blast Floor deals 35% damage on failed checks.*"

            embed.description = (
                f"**{sp.get('emoji', '📖')} Spellbook: {sp['name']}**\n"
                f"*School: {sp.get('school', 'Evocation')} • {elem} • Tier: {sp.get('tier_name', 'Basic')}*\n"
                f"**Cost:** {sp.get('mp_cost', 0)} MP | **Target:** {tt} | **Power:** {power}×\n"
                f"**Accuracy:** {acc_str}{crit_str}{extra_notes}\n\n"
                f"{sp.get('description', 'Study this grimoire to master its arcane mysteries.')}"
            )
        elif effect_raw:
            embed.add_field(name="Description / Effect", value=effect_raw, inline=False)
    elif effect_raw.startswith("[CONSUMABLE_JSON]"):
        from mechanics.combat.items.consumables import parse_consumable_metadata
        c_meta = parse_consumable_metadata(item) or {}
        desc = c_meta.get("effect_desc") or c_meta.get("description") or ""
        tier_num = c_meta.get("tier", 3)
        tier_str = "Tier 1 (Mastercraft)" if tier_num == 1 else ("Tier 2 (Refined)" if tier_num == 2 else "Tier 3 (Standard)")
        info_parts = [f"**Potency:** {tier_str}"]
        if c_meta.get("hp_restore"):
            info_parts.append(f"**Healing:** +{c_meta['hp_restore']} HP")
        if c_meta.get("mp_restore"):
            info_parts.append(f"**Mana Restore:** +{c_meta['mp_restore']} MP")
        if c_meta.get("buffs"):
            b_list = []
            for bk, bv in c_meta["buffs"].items():
                if isinstance(bv, float) and 0 < bv < 1:
                    b_list.append(f"{bk.upper()} +{int(bv*100)}%")
                else:
                    b_list.append(f"{bk.upper()} +{bv}")
            info_parts.append(f"**Buffs:** {', '.join(b_list)}")
        if c_meta.get("cure_status"):
            info_parts.append(f"**Cures:** {', '.join(c_meta['cure_status'])}")
        if c_meta.get("damage"):
            info_parts.append(f"**Damage:** {c_meta['damage']}")
        if desc:
            info_parts.append(f"\n*{desc}*")
        embed.description = "\n".join(info_parts)
    elif effect_raw:
        clean_effect = effect_raw.replace("(flavor only -- confers no stat bonus)", "").replace("Starting weapon (flavor only -- confers no stat bonus).", "").strip()
        if clean_effect:
            embed.add_field(name="Description / Effect", value=clean_effect, inline=False)

    return embed


class InspectItemSelectDropdown(discord.ui.Select):
    def __init__(self, user_id: int, items: list[dict]):
        self.user_id = user_id
        options = []
        seen = set()
        for item in items[:25]:
            name = item["name"]
            if name in seen:
                continue
            seen.add(name)
            icon = get_item_icon(name, item.get("item_type", ""), item.get("effect", ""), item.get("slot", ""))
            options.append(discord.SelectOption(
                label=f"{name}"[:100],
                value=str(item["id"]),
                description=f"Type: {item.get('item_type', 'Item')} | Slots: {item.get('slot_cost', 1)}"[:100],
                emoji=icon
            ))
        super().__init__(placeholder="Choose an item to inspect...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        item_id = int(self.values[0])
        inv = await adb(db.get_inventory, self.user_id)
        match = next((i for i in inv if i["id"] == item_id), None)
        if not match:
            await interaction.response.send_message("❌ Item not found.", ephemeral=True)
            return

        embed = build_item_inspect_embed(match, self.user_id)
        await interaction.response.edit_message(content="", embed=embed, view=None)


class InspectItemSelectView(discord.ui.View):
    def __init__(self, user_id: int, items: list[dict]):
        super().__init__(timeout=120)
        self.add_item(InspectItemSelectDropdown(user_id, items))


# ==============================================================================
# INVENTORY COG COMMANDS
# ==============================================================================

class InventoryCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    inventory_group = app_commands.Group(name="inventory", description="Manage your inventory & equipment")

    # ---------------------------------------------------------- autocomplete
    async def _item_autocomplete(self, interaction: discord.Interaction, current: str):
        inv = await adb(db.get_inventory, interaction.user.id)
        current_lower = current.lower()
        seen = set()
        choices = []
        for item in inv:
            if current_lower and current_lower not in item["name"].lower():
                continue
            if item["name"] in seen:
                continue
            seen.add(item["name"])
            icon = get_item_icon(item["name"], item.get("item_type", ""), item.get("effect", ""), item.get("slot", ""))
            label = f"{icon} {item['name']}"
            if item.get("equipped") and item.get("slot"):
                label += f" (equipped: {item['slot']})"
            choices.append(app_commands.Choice(name=label[:100], value=item["name"]))
            if len(choices) >= 25:
                break
        return choices

    # -------------------------------------------------------------- show
    @inventory_group.command(name="show", description="Open your interactive inventory & equipment dashboard")
    async def show(self, interaction: discord.Interaction):
        char = await adb(db.get_character, interaction.user.id)
        if not char:
            await interaction.response.send_message("❌ You don't have a character yet. Create one with `/character create`.", ephemeral=True)
            return

        embed = build_inventory_embed(interaction.user.id)
        view = InventoryDashboardView(interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view)

    # -------------------------------------------------------------- equip (CLI shortcut)
    @inventory_group.command(name="equip", description="Equip an item into one of your gear slots")
    @app_commands.describe(item_name="The item to equip", slot="Which gear slot to place it in")
    @app_commands.choices(slot=[
        app_commands.Choice(name=f"{EQUIPMENT_SLOT_EMOJI.get(s, '')} {s}".strip(), value=s)
        for s in EQUIPMENT_SLOTS
    ])
    async def equip(self, interaction: discord.Interaction, item_name: str, slot: app_commands.Choice[str]):
        char = await adb(db.get_character, interaction.user.id)
        if not char:
            await interaction.response.send_message("❌ You don't have a character yet.", ephemeral=True)
            return
            
        session_id = await adb(db.get_active_session_id_for_user, interaction.user.id)
        session = (await adb(db.get_session, session_id)) if session_id else {}
        scenario = session.get("scenario", char.get("scenario", "fantasy"))
        inv = await adb(db.get_inventory, interaction.user.id)
        match = next((i for i in inv if i["name"].lower() == item_name.lower()), None)
        if not match:
            await interaction.response.send_message(f"❌ You don't have an item called '{item_name}'.", ephemeral=True)
            return

        from mechanics.combat.items import can_equip_item_in_scenario
        allowed, reason = can_equip_item_in_scenario(match, slot.value, scenario)
        if not allowed:
            await interaction.response.send_message(reason, ephemeral=True)
            return

        try:
            previous = await adb(db.equip_item, interaction.user.id, match["id"], slot.value)
        except ValueError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return

        match_icon = get_item_icon(match["name"], match.get("item_type", ""), match.get("effect", ""), slot.value)
        msg = f"✨ Equipped {match_icon} **{match['name']}** to your **{slot.value}** slot."
        if previous:
            prev_icon = get_item_icon(previous["name"], previous.get("item_type", ""), previous.get("effect", ""), "")
            msg += f" *({prev_icon} {previous['name']} was unequipped and returned to your bag)*"
        await interaction.response.send_message(msg)

    @equip.autocomplete("item_name")
    async def equip_item_autocomplete(self, interaction: discord.Interaction, current: str):
        return await self._item_autocomplete(interaction, current)

    # -------------------------------------------------------------- unequip (CLI shortcut)
    @inventory_group.command(name="unequip", description="Unequip whatever is in one of your gear slots")
    @app_commands.describe(slot="Which gear slot to clear")
    @app_commands.choices(slot=[
        app_commands.Choice(name=f"{EQUIPMENT_SLOT_EMOJI.get(s, '')} {s}".strip(), value=s)
        for s in EQUIPMENT_SLOTS
    ])
    async def unequip(self, interaction: discord.Interaction, slot: app_commands.Choice[str]):
        char = await adb(db.get_character, interaction.user.id)
        if not char:
            await interaction.response.send_message("❌ You don't have a character yet.", ephemeral=True)
            return
        removed = await adb(db.unequip_slot, interaction.user.id, slot.value)
        if not removed:
            await interaction.response.send_message(f"❌ Your **{slot.value}** slot is already empty.", ephemeral=True)
            return
        rem_icon = get_item_icon(removed["name"], removed.get("item_type", ""), removed.get("effect", ""), slot.value)
        await interaction.response.send_message(
            f"🛡️ Unequipped {rem_icon} **{removed['name']}** from your **{slot.value}** slot.")

    # -------------------------------------------------------------- drop (CLI shortcut)
    @inventory_group.command(name="drop", description="Drop/discard an item by name")
    @app_commands.describe(item_name="The item to drop")
    async def drop(self, interaction: discord.Interaction, item_name: str):
        removed = await adb(db.remove_item_by_name, interaction.user.id, item_name)
        if removed:
            await interaction.response.send_message(f"🗑️ Dropped **{item_name}**.")
        else:
            await interaction.response.send_message(f"❌ You don't have an item called '{item_name}'.", ephemeral=True)

    # -------------------------------------------------------------- inspect (CLI shortcut)
    @inventory_group.command(name="inspect", description="Inspect an item in your inventory to view its stats and lore")
    @app_commands.describe(item_name="The item to inspect")
    async def inspect(self, interaction: discord.Interaction, item_name: str):
        char = await adb(db.get_character, interaction.user.id)
        if not char:
            await interaction.response.send_message("❌ You don't have a character yet.", ephemeral=True)
            return
        inv = await adb(db.get_inventory, interaction.user.id)
        match = next((i for i in inv if i["name"].lower() == item_name.lower()), None)
        if not match:
            await interaction.response.send_message(f"❌ You don't have an item called '{item_name}'.", ephemeral=True)
            return

        embed = build_item_inspect_embed(match, interaction.user.id)
        await interaction.response.send_message(embed=embed)

    @inspect.autocomplete("item_name")
    async def inspect_item_autocomplete(self, interaction: discord.Interaction, current: str):
        return await self._item_autocomplete(interaction, current)


async def setup(bot: commands.Bot):
    await bot.add_cog(InventoryCog(bot))
