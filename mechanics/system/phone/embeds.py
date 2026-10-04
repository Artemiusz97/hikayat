from __future__ import annotations
import json
import logging
import random
import re
import time
import discord
from discord import app_commands
import db
import scenario_data
from llm_client import call_llm_json
log = logging.getLogger("hikayat.phone")
from skill_check import resolve_check, success_chance, CheckResult


PHONE_BRANDING = {
    "high_school_drama": {
        "device_name": "📱 Smartphone",
        "os_name": "SmartOS v4.2",
        "feed_app_name": "PeerPulse",
        "feed_emoji": "📶",
        "dm_app_name": "Line Messenger",
        "contacts_app_name": "Student Directory",
        "gallery_app_name": "Photo Vault",
        "gallery_emoji": "📸",
        "bounty_app_name": "Campus Requests",
        "shop_app_name": "SchoolMart Delivery",
        "emoji": "📱",
        "color": discord.Color.teal()
    },
    "cyberpunk": {
        "device_name": "📟 Cyberdeck",
        "os_name": "NeuroDeck OS v9",
        "feed_app_name": "NetWire",
        "feed_emoji": "🌐",
        "dm_app_name": "Encrypted Comm",
        "contacts_app_name": "Net Directory",
        "gallery_app_name": "Holovault",
        "gallery_emoji": "💾",
        "bounty_app_name": "FixerNet Gigs",
        "shop_app_name": "DarkNet Market",
        "emoji": "📟",
        "color": discord.Color.purple()
    },
    "sci_fi": {
        "device_name": "📡 Comms Pad",
        "os_name": "StellarComm Link",
        "feed_app_name": "GalactiNet",
        "feed_emoji": "📡",
        "dm_app_name": "Subspace Link",
        "contacts_app_name": "Personnel Log",
        "gallery_app_name": "Media Archive",
        "gallery_emoji": "🎞️",
        "bounty_app_name": "Stellar Bounties",
        "shop_app_name": "Orbital Supplies",
        "emoji": "📡",
        "color": discord.Color.blue()
    },
    "steampunk": {
        "device_name": "⚙️ Telegraph Pad",
        "os_name": "Aetheric Dispatch",
        "feed_app_name": "The Aether Club",
        "feed_emoji": "⚙️",
        "dm_app_name": "Telegraph Relay",
        "contacts_app_name": "Address Ledger",
        "gallery_app_name": "Daguerreotype Album",
        "gallery_emoji": "📷",
        "bounty_app_name": "Dispatch Board",
        "shop_app_name": "Mail-Order Ledger",
        "emoji": "⚙️",
        "color": discord.Color.dark_gold()
    },
    "general_modern": {
        "device_name": "📱 Smartphone",
        "os_name": "Mobile OS",
        "feed_app_name": "EchoFeed",
        "feed_emoji": "📱",
        "dm_app_name": "Messenger",
        "contacts_app_name": "Contacts",
        "gallery_app_name": "Gallery",
        "gallery_emoji": "🖼️",
        "bounty_app_name": "GigBoard",
        "shop_app_name": "QuickDelivery Store",
        "emoji": "📱",
        "color": discord.Color.teal()
    }
}

def scenario_has_smartphone(scen_key: str) -> bool:
    """Checks if the scenario supports smartphone or cyberdeck hub devices via modular mechanics."""
    if not scen_key:
        return False
    from scenario_data import is_mechanic_enabled
    return is_mechanic_enabled(scen_key, "smartphone_hub")

def get_phone_branding(scen_key: str) -> dict:
    """Returns scenario-specific UI titles, app names, and emojis for the phone."""
    scen = str(scen_key or "").lower()
    from scenario_data import has_tag
    if has_tag(scen_key, "high_school") or has_tag(scen_key, "high_school_drama") or "school" in scen:
        return PHONE_BRANDING["high_school_drama"]
    if has_tag(scen_key, "cyberpunk") or "cyber" in scen:
        return PHONE_BRANDING["cyberpunk"]
    if has_tag(scen_key, "space") or has_tag(scen_key, "sci_fi") or "space" in scen:
        return PHONE_BRANDING["sci_fi"]
    if has_tag(scen_key, "steampunk") or "steam" in scen:
        return PHONE_BRANDING["steampunk"]
    return PHONE_BRANDING["general_modern"]

def build_media_gallery_embed(session_id: int, user_id: int, filter_contact: str = None, filter_type: str = None, page: int = 0) -> discord.Embed:
    """Builds a paginated visual embed listing all saved digital media items in the player's phone."""
    session = db.get_session(session_id)
    scen_key = session.get("scenario", "fantasy") if session else "fantasy"
    branding = get_phone_branding(scen_key)
    app_name = branding.get("gallery_app_name", "Photo Vault")
    app_emoji = branding.get("gallery_emoji", "📸")

    inv_items = db.get_inventory(user_id) if user_id else []
    from mechanics.combat.items import is_digital_item, parse_digital_item_metadata
    all_digital = [it for it in inv_items if is_digital_item(it)]

    # Apply Contact filter
    if filter_contact and filter_contact != "ALL":
        filtered = []
        for it in all_digital:
            m = parse_digital_item_metadata(it) or {}
            c_name = m.get("contact_name") or ""
            if c_name.lower() == filter_contact.lower() or filter_contact.lower() in it.get("name", "").lower():
                filtered.append(it)
    else:
        filtered = all_digital

    # Apply Category filter
    if filter_type:
        ft_low = filter_type.lower()
        cat_filtered = []
        for it in filtered:
            m = parse_digital_item_metadata(it) or {}
            m_type = str(m.get("media_type") or "").lower()
            name_l = it.get("name", "").lower()
            if ft_low == "photos":
                if "video" not in m_type and "video" not in name_l and "nsfw" not in m_type and "intimate" not in name_l:
                    cat_filtered.append(it)
            elif ft_low == "intimate":
                if "nsfw" in m_type or "intimate" in m_type or "intimate" in name_l or "🔞" in name_l:
                    cat_filtered.append(it)
            elif ft_low == "videos":
                if "video" in m_type or "video" in name_l:
                    cat_filtered.append(it)
        filtered = cat_filtered

    total_count = len(filtered)
    page_size = 5
    max_pages = max(1, (total_count + page_size - 1) // page_size)
    page = max(0, min(page, max_pages - 1))
    paged_items = filtered[page * page_size : (page + 1) * page_size]

    contact_label = filter_contact if filter_contact and filter_contact != "ALL" else "All Contacts"
    type_label = filter_type.capitalize() if filter_type else "All Media"

    embed = discord.Embed(
        title=f"{app_emoji} {app_name} — Encrypted Storage",
        description=(
            f"**Vault Status:** `{total_count}` items saved • **Filter:** `{contact_label}` • `{type_label}`\n"
            f"**Page:** `{page + 1} / {max_pages}` • *All media takes 0 inventory weight.*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        color=branding["color"]
    )

    if not paged_items:
        embed.add_field(
            name="Empty Album",
            value="*No photos or videos match this filter. Receive media in DMs or capture photos in the story!*",
            inline=False
        )
    else:
        for idx, it in enumerate(paged_items, start=page * page_size + 1):
            m = parse_digital_item_metadata(it) or {}
            caption = m.get("caption") or it.get("effect", "")
            if caption.startswith("[DIGITAL_JSON]"):
                caption = it.get("name", "")
            c_sender = m.get("contact_name") or "Story Subject"
            m_type = m.get("media_type") or "photo"
            ts = m.get("timestamp")
            time_str = time.strftime("%b %d, %H:%M", time.localtime(ts)) if ts else "Recent"

            type_icon = "🔞" if "nsfw" in m_type or "intimate" in m_type else ("📹" if "video" in m_type else "📸")
            short_cap = (caption[:110] + "...") if len(caption) > 110 else caption
            embed.add_field(
                name=f"#{idx} {type_icon} {it['name']}",
                value=f"> *\"{short_cap}\"*\n👤 **From:** {c_sender} • 📅 *{time_str}*",
                inline=False
            )

    embed.set_footer(text="Select a photo/video from the dropdown to view in full resolution:")
    return embed

def _build_media_item_detail_embed(item: dict) -> discord.Embed:
    """Builds a full-resolution visual card for an individual photo or video item."""
    from mechanics.combat.items import parse_digital_item_metadata
    d_meta = parse_digital_item_metadata(item) or {}
    caption = d_meta.get("caption") or item.get("effect", "")
    if caption.startswith("[DIGITAL_JSON]"):
        caption = item.get("name", "")
    contact_name = d_meta.get("contact_name", "Unknown Contact")
    media_type = d_meta.get("media_type", "photo")
    tags = d_meta.get("tags", ["misc", "digital"])
    ts = d_meta.get("timestamp")
    time_str = time.strftime("%B %d, %Y at %H:%M", time.localtime(ts)) if ts else "Recent"

    if "video" in media_type and ("nsfw" in media_type or "intimate" in media_type):
        type_title = "🔞 Intimate Video Clip"
        color = discord.Color.red()
        icon = "🔞"
    elif "video" in media_type:
        type_title = "📹 High-Def Video Clip"
        color = discord.Color.blue()
        icon = "📹"
    elif "nsfw" in media_type or "intimate" in media_type:
        type_title = "🔞 Intimate Photo"
        color = discord.Color.magenta()
        icon = "🔞"
    else:
        type_title = "📸 Digital Photo"
        color = discord.Color.teal()
        icon = "📸"

    embed = discord.Embed(
        title=f"{icon} {item['name']}",
        color=color
    )
    embed.add_field(name="Category / Format", value="`Misc` (0 Slots • Digital Asset)", inline=True)
    embed.add_field(name="Sender / Subject", value=f"**{contact_name}**", inline=True)
    embed.add_field(name="Media Type", value=f"`{type_title}`", inline=True)
    embed.add_field(name="Date Captured", value=f"*{time_str}*", inline=True)
    embed.add_field(name="Tags", value=" ".join(f"`#{t}`" for t in tags), inline=True)
    embed.add_field(name="Device Storage", value="`Encrypted Local Vault` 📱", inline=True)

    embed.add_field(
        name="🖼️ Visual Description & Transcript",
        value=f"> *\"{caption}\"*",
        inline=False
    )
    embed.set_footer(text="Digital media is stored on your device. Tap buttons below to manage:")
    return embed

def build_phone_home_embed(session_id: int, user_id: int) -> discord.Embed:
    session = db.get_session(session_id)
    scen_key = session.get("scenario", "fantasy") if session else "fantasy"
    branding = get_phone_branding(scen_key)
    char = db.get_character(user_id)
    contacts = db.get_contacts(session_id, character_id=char.get("id", 0)) if char else []

    embed = discord.Embed(
        title=f"{branding['emoji']} {branding['device_name']} — {branding['os_name']}",
        description=f"**User:** {char.get('name', 'Hero') if char else 'Player'} • **Battery:** 98% 🔋 • **Signal:** 5G 📶\n"
                    f"**Location:** {session.get('current_location', 'Unknown')}\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        color=branding["color"]
    )

    contacts_title = branding.get("contacts_app_name", "Contacts")
    embed.add_field(
        name=f"👥 {contacts_title}",
        value=f"View relationship standings, traits, preferences, and profiles.",
        inline=True
    )
    embed.add_field(
        name=f"💬 {branding['dm_app_name']}",
        value=f"**{len(contacts)}** Contacts saved. Text friends or flirt for intel.",
        inline=True
    )
    embed.add_field(
        name=f"{branding['feed_emoji']} {branding['feed_app_name']}",
        value=f"Social timeline & peer buzz. Dig for rumors or discover contacts.",
        inline=True
    )

    # Gallery / Photo Vault status
    inv_items = db.get_inventory(user_id) if user_id else []
    from mechanics.combat.items import is_digital_item, parse_digital_item_metadata
    digital_media = [it for it in inv_items if is_digital_item(it)]
    photo_count = sum(1 for it in digital_media if "video" not in (parse_digital_item_metadata(it) or {}).get("media_type", "photo").lower())
    video_count = len(digital_media) - photo_count
    gallery_title = branding.get("gallery_app_name", "Photo Vault")
    gallery_emoji = branding.get("gallery_emoji", "📸")
    if digital_media:
        gallery_summary = f"**{len(digital_media)}** items ({photo_count} photos, {video_count} videos) in encrypted vault."
    else:
        gallery_summary = "Empty. Photos and videos received or captured will appear here."

    embed.add_field(
        name=f"{gallery_emoji} {gallery_title}",
        value=gallery_summary,
        inline=True
    )
    embed.add_field(
        name=f"📋 {branding['bounty_app_name']}",
        value=f"Accept dynamic commissions & side gigs directly on your device.",
        inline=True
    )
    embed.add_field(
        name=f"🛍️ {branding['shop_app_name']}",
        value=f"Order snacks, healing items, gear, and supplies delivered to your bag.",
        inline=True
    )

    embed.set_footer(text="Tap an App button below to open:")
    return embed

def _build_dm_chat_embed(session_id: int, contact: dict, last_reply: dict = None) -> discord.Embed:
    name = contact.get("name", "Contact")
    score = contact.get("relationship_score", 0)
    track = contact.get("track", "platonic").capitalize()
    basic = contact.get("basic_info", {})
    role = basic.get("role") or basic.get("occupation") or "Contact"
    npc_id = contact.get("npc_id") or name.lower().replace(" ", "_")

    messages = db.get_phone_messages(session_id, npc_id, limit=8)

    score_sign = f"+{score}" if score > 0 else str(score)
    embed = discord.Embed(
        title=f"💬 Direct Messages: {name}",
        description=f"**Role:** {role} • **Affinity:** `{score_sign}` ({track})\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        color=discord.Color.teal() if score >= 0 else discord.Color.red()
    )

    if not messages:
        embed.add_field(
            name="Message History",
            value="*No messages yet. Send a text using the buttons below!*",
            inline=False
        )
    else:
        chat_lines = []
        for m in messages:
            sender_tag = "🧑 **You**" if m["sender"] == "player" else f"👤 **{name}**"
            msg_text = m["message"]
            if "[Attached Intimate Video:" in msg_text:
                prefix, _, vid_body = msg_text.partition("[Attached Intimate Video:")
                vid_content, _, suffix = vid_body.partition("]")
                suffix_line = f"\n{suffix.strip()}" if suffix.strip() else ""
                msg_text = f"{prefix.strip()}\n> 🔞 **[Intimate Video]:** *{vid_content.strip()}*{suffix_line}".strip()
            elif "[Attached Video:" in msg_text:
                prefix, _, vid_body = msg_text.partition("[Attached Video:")
                vid_content, _, suffix = vid_body.partition("]")
                suffix_line = f"\n{suffix.strip()}" if suffix.strip() else ""
                msg_text = f"{prefix.strip()}\n> 📹 **[Video]:** *{vid_content.strip()}*{suffix_line}".strip()
            elif "[Attached Intimate Photo:" in msg_text:
                prefix, _, photo_body = msg_text.partition("[Attached Intimate Photo:")
                photo_content, _, suffix = photo_body.partition("]")
                suffix_line = f"\n{suffix.strip()}" if suffix.strip() else ""
                msg_text = f"{prefix.strip()}\n> 🔞 **[Intimate Photo]:** *{photo_content.strip()}*{suffix_line}".strip()
            elif "[Attached Photo:" in msg_text:
                prefix, _, photo_body = msg_text.partition("[Attached Photo:")
                photo_content, _, suffix = photo_body.partition("]")
                suffix_line = f"\n{suffix.strip()}" if suffix.strip() else ""
                msg_text = f"{prefix.strip()}\n> 📸 **[Photo]:** *{photo_content.strip()}*{suffix_line}".strip()
            chat_lines.append(f"{sender_tag}: {msg_text}")
        embed.add_field(
            name="💬 Recent Texts",
            value="\n\n".join(chat_lines)[-1000:],
            inline=False
        )

    if last_reply:
        delta = last_reply.get("affinity_delta", 0)
        delta_str = f"+{delta}" if delta > 0 else str(delta)
        check = last_reply.get("check_result")
        lines = []
        if check:
            tier_emoji = {
                "crit_success": "⭐⭐",
                "success": "🎯",
                "fail": "❌",
                "crit_fail": "💀"
            }.get(check.get("tier"), "🎲")
            lines.append(f"🎲 **{check['stat']} Check ({check['chance']}%)**: {tier_emoji} {check['tier_label']}")

        status_parts = [f"Affinity: `{delta_str}` (New: `{last_reply.get('new_score', score)}`)"]
        is_rom = last_reply.get("is_romantic") or (contact.get("track", "platonic").lower() == "romantic")
        if last_reply.get("rendezvous_location") and last_reply.get("intent") == "meetup":
            icon = "🌹 Date" if is_rom else "📍 Rendezvous"
            status_parts.append(f"{icon}: **{last_reply['rendezvous_location']}**")
        elif check and not check.get("succeeded") and last_reply.get("intent") == "meetup":
            status_parts.append("*(Date declined)*" if is_rom else "*(No meetup proposed)*")
        elif last_reply.get("intent") == "nsfw_photo":
            if check and check.get("succeeded"):
                status_parts.append("🔞 **Intimate Photo Exchanged**")
            else:
                status_parts.append("*(Photo declined)*")
        elif last_reply.get("intent") == "photo":
            status_parts.append("📸 **Photo Exchanged**")

        if last_reply.get("digital_item_id"):
            m_type = last_reply.get("media_type_created", "photo")
            if "video" in m_type:
                status_parts.append("💾 `Video Saved to /inventory`")
            elif "nsfw" in m_type or "intimate" in m_type:
                status_parts.append("💾 `Photo Saved to /inventory`")
            else:
                status_parts.append("💾 `Photo Saved to /inventory`")

        lines.append(" | ".join(status_parts))

        embed.add_field(
            name="⚡ Social Impact",
            value="\n".join(lines),
            inline=False
        )

    embed.set_footer(text="Choose a quick prompt or type a custom message:")
    return embed

def _build_gossip_feed_embed(session: dict, posts: list[dict], branding: dict, charges: int = 3) -> discord.Embed:
    from mechanics.world.locations import get_zone_location_name
    loc = get_zone_location_name(session.get("current_location", "Local Area"))
    embed = discord.Embed(
        title=f"{branding['feed_emoji']} {branding['feed_app_name']} — Timeline & Social Hub",
        description=f"Trending discussions and peer updates around **{loc}**:\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        color=branding["color"]
    )

    for idx, p in enumerate(posts[:5], 1):
        author = p.get("author_name", "Anonymous")
        handle = p.get("author_handle", "@anon")
        content = p.get("content", "")
        time_ago = p.get("time_ago", "Just now")
        tag = f" `{p['tag']}`" if p.get("tag") else ""
        likes = p.get("likes", random.randint(10, 45))

        val = f"{content}\n❤️ **{likes}** • *{time_ago}*{tag}"

        embed.add_field(
            name=f"#{idx} {author} ({handle})",
            value=val,
            inline=False
        )

    embed.set_footer(text=f"Rumor Searches: {charges}/3 (Resets every 5 turns) • Tap buttons below:")
    return embed

def _build_social_profile_embed(session_id: int, profile: dict, branding: dict) -> discord.Embed:
    is_faculty = profile.get("is_faculty", False)
    name = profile.get("name", "Student")
    handle = profile.get("handle", "@user")
    role = profile.get("role", "Student")
    grade = profile.get("grade", "Student")
    club = profile.get("club", "None")
    clique = profile.get("clique", "General")
    facility = profile.get("facility", "Westlake Academy")
    bio = profile.get("personality", "")
    mutuals = profile.get("mutual_friends", [])
    is_already = profile.get("is_already_contact", False)
    cooldown = profile.get("cooldown_turns_left", 0)

    embed = discord.Embed(
        title=f"👤 {name} ({handle})",
        color=discord.Color.dark_grey() if is_faculty else (discord.Color.gold() if is_already else branding["color"])
    )

    if is_faculty:
        embed.description = (
            f"🏛️ **Faculty & Staff Official Directory**\n"
            f"**Role:** {role} • **Location:** {facility}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"**Staff Record:** *\"{bio}\"*\n\n"
            f"🔒 **Account Policy:** *Under Academy digital safety regulations, faculty accounts are restricted from student friend circles.*"
        )
    else:
        mutual_str = ", ".join(mutuals) if mutuals else "*None (Total Stranger)*"
        if profile.get("is_sibling_friend"):
            mutual_str += f" *(Sibling: {profile.get('sibling_name')})*"

        status_str = "✅ **In Your Contacts** (Line Messenger unlocked)" if is_already else (
            f"⏳ **Request Pending / Declined** ({cooldown} turn(s) cooldown)" if cooldown > 0 else
            "✨ *Not yet connected. Tap 'Send Friend Request' below!*"
        )

        embed.description = (
            f"**Year/Grade:** {grade} • **Role:** {role}\n"
            f"**Club / Clique:** {club} ({clique})\n"
            f"**Primary Hangout:** {facility}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"**Bio / Mannerisms:** *\"{bio}\"*\n\n"
            f"👥 **Mutual Friends ({len(mutuals)}):** {mutual_str}\n"
            f"📱 **Status:** {status_str}"
        )

    embed.set_footer(text=f"{branding['feed_app_name']} Profile Lookup")
    return embed

