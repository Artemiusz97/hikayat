import asyncio
import json
import logging
import random
import re
import time
import discord
from mechanics.world.locations import format_tiered_location_string
from discord import app_commands
from discord.ext import commands
logger = logging.getLogger("hikayat.adventure")
import db
from db import adb
import game_engine
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


MODE_LABELS = {"solo": "Solo", "turn": "Multiplayer (Turn-based)", "sync": "Multiplayer (Synchronized)"}

_RESULT_COLORS = {
    "crit_success": discord.Color.from_rgb(46, 204, 113),   # emerald green
    "success":      discord.Color.from_rgb(26, 188, 156),   # teal
    "fail":         discord.Color.from_rgb(230, 126, 34),   # amber
    "crit_fail":    discord.Color.from_rgb(231, 76, 60),    # crimson
}

_RESULT_TITLES = {
    "crit_success": "✨ CRITICAL SUCCESS",
    "success":      "🎯 SUCCESS",
    "fail":         "⚠️ FAILURE",
    "crit_fail":    "💥 CRITICAL FAILURE",
}

def _scenario_command_choices() -> list[app_commands.Choice[str]]:
    try:
        choices = []
        for key, entry in load_scenarios().items():
            if key.startswith("custom_combinator_"):
                continue
            tags = entry.get("tags", [])
            tag_badges = ""
            name_lower = entry["name"].lower()
            if "nsfw" in tags and "nsfw" not in name_lower: tag_badges += " [NSFW]"
            elif "sfw" in tags and "sfw" not in name_lower: tag_badges += " [SFW]"
            if "furry" in tags and "furry" not in name_lower: tag_badges += " [Furry]"
            if ("space" in tags or "sci_fi" in tags) and "space" not in name_lower and "sci-fi" not in name_lower and "sci_fi" not in name_lower: tag_badges += " [Space]"
            if "cyberpunk" in tags and "cyberpunk" not in name_lower: tag_badges += " [Cyberpunk]"
            name = f"{entry['name']}{tag_badges}"[:100]
            choices.append(app_commands.Choice(name=name, value=key))
        choices.append(app_commands.Choice(name="🛠️ Custom Scenario (Use Tags Parameter)", value="custom"))
        return choices
    except ScenarioError:
        return [
            app_commands.Choice(name="Fantasy", value=DEFAULT_SCENARIO),
            app_commands.Choice(name="🛠️ Custom Scenario (Use Tags Parameter)", value="custom")
        ]

def _parse_status_effects(raw) -> list:
    """`char['status_effects']` is stored as a JSON-encoded string (see
    db.set_status_effects) -- this decodes it back into a plain list for
    display, tolerating a value that's already a list, or empty/malformed
    input."""
    if isinstance(raw, list):
        return raw
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, list) else []
    except (TypeError, ValueError):
        return []

def _party_vitals_text(session: dict) -> str:
    """Renders the tracker: Lvl, Name, HP/MaxHP, MP/MaxMP, and
    active status effects for every human player and recruited party companion."""
    lines = []
    for uid in session.get("turn_order", []):
        char = db.get_character(uid)
        if not char:
            continue
        marker = ""
        if session.get("mode") != "sync" and uid == db.current_turn_user_id(session):
            marker = "▶️ "
        status = _parse_status_effects(char.get("status_effects"))
        status_text = ", ".join(str(s.get("name", s)) if isinstance(s, dict) else str(s) for s in status if s) if status else "None"
        lines.append(f"{marker}Lvl {char.get('level', 1)} **{char.get('name', 'Hero')}** — ❤️ {char.get('hp', 100)}/{char.get('max_hp', 100)} | "
                     f"💙 {char.get('mp', 50)}/{char.get('max_mp', 50)} | Status: {status_text}")

    scen_key = session.get("scenario", "fantasy")
    from scenario_data import is_mechanic_enabled
    if is_mechanic_enabled(scen_key, "tactical_combat"):
        party_npcs = session.get("party_npcs") or []
        for npc in party_npcs:
            if isinstance(npc, dict) and npc.get("name"):
                lvl = npc.get("level", 1)
                hp = npc.get("hp", 20)
                max_hp = npc.get("max_hp", hp)
                mp = npc.get("mp", 10)
                max_mp = npc.get("max_mp", mp)
                status = _parse_status_effects(npc.get("status_effects"))
                status_text = ", ".join(str(s.get("name", s)) if isinstance(s, dict) else str(s) for s in status if s) if status else "None"
                role_tag = f" ({npc['role']})" if npc.get("role") else ""
                lines.append(f"🤝 Lvl {lvl} **{npc['name']}**{role_tag} — ❤️ {hp}/{max_hp} | "
                             f"💙 {mp}/{max_mp} | Status: {status_text}")

    return _truncate_field_value("\n".join(lines), 1024)

def _location_text(session: dict, char_name: str = "") -> str:
    loc = session.get("current_location") or "Unknown"
    from mechanics.world.locations import is_transit_location, parse_tiered_location, format_tiered_location_string, get_zone_emoji
    if is_transit_location(loc):
        return _truncate_field_value(loc, 1024)
    scen_key = session.get("scenario", "high_school_drama")
    z, p, s = parse_tiered_location(loc, scen_key, session_id=session.get("id", 0), char_name=char_name)
    z_emoji = get_zone_emoji(z, scen_key)
    loc_str = f"{z_emoji} {format_tiered_location_string(z, p, s)}"
    return _truncate_field_value(loc_str, 1024)

def _safe_int(val, default=None) -> int | None:
    if val is None:
        return default
    if isinstance(val, int) and not isinstance(val, bool):
        return val
    if isinstance(val, float):
        return int(val)
    if isinstance(val, str):
        cleaned = val.strip().lstrip("+")
        try:
            return int(cleaned)
        except (ValueError, TypeError):
            pass
    return default

def _truncate_field_value(text: str, max_len: int = 1024) -> str:
    if not text:
        return "—"
    text_str = str(text)
    if len(text_str) <= max_len:
        return text_str
    return text_str[:max_len - 4].rstrip() + "..."

def _truncate_field_name(name: str, max_len: int = 256) -> str:
    if not name:
        return "Field"
    name_str = str(name)
    if len(name_str) <= max_len:
        return name_str
    return name_str[:max_len - 4].rstrip() + "..."

def _safe_add_field(embed: discord.Embed, name: str, value: str, inline: bool = False):
    """Safely adds a field to a discord.Embed, guaranteeing name <= 256 and value <= 1024."""
    embed.add_field(
        name=_truncate_field_name(name, 256),
        value=_truncate_field_value(value, 1024),
        inline=inline
    )

def _norm_name(text: str) -> str:
    if not text:
        return ""
    return unicodedata.normalize('NFKD', str(text)).encode('ASCII', 'ignore').decode('utf-8').strip().lower()

def _is_dialogue_partner(name: str, dialogue_partners: list | str = None) -> bool:
    if not name or not dialogue_partners:
        return False
    if isinstance(dialogue_partners, str):
        try:
            parsed = json.loads(dialogue_partners)
            partners_list = parsed if isinstance(parsed, list) else [dialogue_partners]
        except Exception:
            partners_list = [dialogue_partners]
    elif isinstance(dialogue_partners, list):
        partners_list = []
        for p in dialogue_partners:
            if isinstance(p, list):
                partners_list.extend(str(x) for x in p if x)
            elif p:
                partners_list.append(str(p))
    else:
        partners_list = [str(dialogue_partners)]

    n_raw = name.strip().lower()
    n_clean = _norm_name(name)
    title_words = {
        "the", "elder", "lord", "lady", "sir", "madam", "captain", "dr", "mr", "ms", "mrs",
        "scholar", "guardian", "druid", "student", "council", "president", "vice", "secretary",
        "representative", "officer", "member", "guildmaster", "archivist", "warden"
    }
    n_tokens = [t for t in n_clean.split() if len(t) > 2 and t not in title_words]
    if not n_tokens and len(n_clean) > 2:
        n_tokens = [n_clean]

    for p in partners_list:
        p_raw = str(p).strip().lower()
        p_clean = _norm_name(p)
        if p_raw in n_raw or n_raw in p_raw or p_clean in n_clean or n_clean in p_clean:
            return True
        for t in n_tokens:
            if t in p_clean or t in p_raw:
                return True
    return False

def is_matching_contact_dialogue_partner(contact: dict, partner_str: str) -> bool:
    """Returns True if the contact matches the specified dialogue partner string.
    Ensures that shared family surnames do not cause false positives (e.g. Amanda vs Sofia Anderson)."""
    if not contact or not partner_str:
        return False
    p_raw = str(partner_str).strip()
    if not p_raw or p_raw.lower() in ("none", "null"):
        return False

    c_name = str(contact.get("name") or "").strip()
    c_nid = str(contact.get("npc_id") or "").strip()

    p_norm = p_raw.lower().replace("_", " ")
    c_name_norm = c_name.lower().replace("_", " ")
    c_nid_norm = c_nid.lower().replace("_", " ")

    if p_norm in (c_name_norm, c_nid_norm):
        return True

    title_words = {
        "the", "elder", "lord", "lady", "sir", "madam", "captain", "dr", "mr", "ms", "mrs", "miss",
        "prof", "professor", "scholar", "guardian", "druid", "student", "council", "president", "vice",
        "secretary", "representative", "officer", "member", "guildmaster", "archivist", "warden", "coach"
    }

    import re
    def clean_tokens(s: str) -> list[str]:
        cleaned = re.sub(r"[^a-zA-Z0-9\s]", " ", s).lower()
        return [t for t in cleaned.split() if t and t not in title_words]

    p_tokens = clean_tokens(p_norm)
    c_tokens = clean_tokens(c_name_norm)
    c_nid_tokens = clean_tokens(c_nid_norm)

    if not p_tokens or not (c_tokens or c_nid_tokens):
        return False

    for target_tokens in (c_tokens, c_nid_tokens):
        if not target_tokens:
            continue
        if p_tokens == target_tokens:
            return True
        if len(p_tokens) >= 2 and len(target_tokens) >= 2:
            if p_tokens[0] == target_tokens[0] and p_tokens[-1] == target_tokens[-1]:
                return True
            if p_tokens[0] != target_tokens[0]:
                continue
        if len(p_tokens) == 1 and p_tokens[0] == target_tokens[0]:
            return True
        if len(target_tokens) == 1 and target_tokens[0] == p_tokens[0]:
            return True

    return False

def _format_tracker_entity(entity: dict, dialogue_partners: list = None, show_vitals: bool = True) -> str:
    """Formats a single entity line for the dashboard tracker fields.
    If the entity is an active dialogue partner, prepends a talking indicator 💬.
    In non-combat scenarios (show_vitals=False), suppresses HP, MP, and Level."""
    name = entity.get("name") or "Unknown"
    role = str(entity.get("role") or "").strip()
    if role.lower() in ("none", "null", "unknown", ""):
        role = ""
    level = _safe_int(entity.get("level"))
    hp = _safe_int(entity.get("hp"))
    max_hp = _safe_int(entity.get("max_hp"), default=hp)
    mp = _safe_int(entity.get("mp"))
    max_mp = _safe_int(entity.get("max_mp"), default=mp)
    status = entity.get("status_effects") or []
    mood = entity.get("mood")

    # In non-combat scenarios, always hide HP, MP, and combat level
    if not show_vitals:
        hp = None
        mp = None
        level = None
    else:
        # In combat scenarios, hide negative/zero sentinel HP
        if hp is not None and hp <= 0:
            hp = None
            mp = None

    role_str = f" ({role})" if role else ""
    is_conv = _is_dialogue_partner(name, dialogue_partners)
    conv_prefix = "💬 " if is_conv else ""

    tier_rank = entity.get("tier_rank")
    tier_name = str(entity.get("tier") or "").lower()
    tier_badge = ""
    if tier_rank == 5 or tier_name == "boss":
        tier_badge = " `[Boss]`"
    elif tier_rank == 4 or tier_name == "miniboss":
        tier_badge = " `[Miniboss]`"
    elif tier_rank == 3 or tier_name == "elite":
        tier_badge = " `[Elite]`"

    intent = entity.get("intent")
    intent_line = f"\n   ↳ ⚡ *Intent: {intent}*" if intent else ""

    status_items = [str(s.get("name", s)) if isinstance(s, dict) else str(s) for s in status if s]
    if mood and str(mood).strip() and str(mood).strip() not in status_items:
        status_items.append(str(mood).strip())

    if hp is not None or level is not None:
        line = f"Lvl {level} " if level is not None else ""
        line += f"{conv_prefix}**{name}**{tier_badge}{role_str}"
        if hp is not None:
            line += f" — ❤️ {hp}/{max_hp}"
            if mp is not None and mp > 0:
                line += f" | 💙 {mp}/{max_mp}"
        status_text = ", ".join(status_items) if status_items else "None"
        line += f" | Status: {status_text}"
        line += intent_line
        return line
    else:
        status_text = ", ".join(status_items) if status_items else "Neutral"
        return f"{conv_prefix}**{name}**{tier_badge}{role_str} | Status: {status_text}{intent_line}"


def _tracker_group_text(entities: list, max_len: int = 1000, dialogue_partners: list = None, show_vitals: bool = True) -> str:
    lines = []
    current_len = 0
    for e in entities:
        line = _format_tracker_entity(e, dialogue_partners=dialogue_partners, show_vitals=show_vitals)
        add_len = len(line) + (1 if lines else 0)
        if current_len + add_len > max_len - 25:
            remaining = len(entities) - len(lines)
            if remaining > 0:
                lines.append(f"... and {remaining} more")
            break
        lines.append(line)
        current_len += add_len
    result = "\n".join(lines)
    return _truncate_field_value(result, max_len)

def _strip_leading_emojis(text: str) -> str:
    """Strips leading emoji characters, unicode symbols, or bracketed stat/quest tags from label text."""
    if not text:
        return ""
    import re
    cleaned = re.sub(r'^(?:[\U00010000-\U0010ffff\u2600-\u27bf\u2300-\u23ff\u2b50\u2b55\u200d\ufe0f\s]+|\s*\[[A-Za-z0-9/ _-]+\]\s*)+', '', str(text)).strip()
    return cleaned if cleaned else str(text).strip()

def _get_choice_quest_icon(choice: dict) -> str | None:
    """Returns the quest/bounty/interaction progression icon (⭐, 🎯, ⚡, 💌, 🎭, 💖, 🎲) if applicable, else None."""
    if not isinstance(choice, dict):
        return None
    raw_label = str(choice.get("label") or choice.get("text") or choice.get("action") or "")
    raw_l = raw_label.lower()
    qid = str(choice.get("quest_id", ""))
    ctype = str(choice.get("contract_type", "")).lower()

    # 1. Story Climax
    if choice.get("is_climax_action") or ctype == "climax" or "⚡" in raw_label or "[story climax]" in raw_l:
        return "⚡"

    # 2. Story Quest Actions
    if "⭐" in raw_label or "[story quest]" in raw_l or "sq-" in qid.lower() or "story" in ctype or choice.get("is_story_quest"):
        return "⭐"

    # 3. Bounty / Sub-Quest Actions
    if choice.get("is_quest_action") or ctype in ("sub_quest", "bounty", "side_bounty", "waypoint", "skill_check", "arrival", "resource_progress") or "🎯" in raw_label or "[bounty]" in raw_l or "bnt-" in qid.lower() or "qst-" in qid.lower():
        if any(b in raw_l for b in ("contract board", "notice board", "bounty board", "bulletin board", "quest board")):
            return None
        return "🎯"

    # 4. Meetup / Phone appointment
    if "💌" in raw_label or "[meetup]" in raw_l:
        return "💌"

    # 5. Social & Character Interaction Archetypes
    if "🎭" in raw_label or "[banter]" in raw_l or any(k in raw_l for k in ("playfully tease", "crack a joke", "crack a playful", "lighthearted joke", "witty banter", "playful joke")):
        return "🎭"
    if "💖" in raw_label or "[affection]" in raw_l or "[flirt]" in raw_l or any(k in raw_l for k in ("flirt with", "compliment ", "sincere compliment", "confess feelings", "affectionate", "hold hands with")):
        return "💖"
    if "🎲" in raw_label or "[challenge]" in raw_l or any(k in raw_l for k in ("challenge ", "arm-wrestle", "friendly wager", "friendly spar")):
        return "🎲"
    if "💬" in raw_label or "[inquiry]" in raw_l or any(k in raw_l for k in ("inquire about", "ask about", "ask if", "ask her", "ask him", "ask them")) or ("ask " in raw_l and " about " in raw_l):
        return "💬"

    return None

def _get_choice_skill_emoji(choice: dict) -> str:
    """Returns the skill check or action icon (e.g. 🧠, 💪, 🏹, 🗣️, 👁️, 🛡️, 🍀, 💬, 🔍, 🚶, 🎒, ✨)."""
    if not isinstance(choice, dict):
        return "✨"
    stat = str(choice.get("stat", "")).upper()
    req = choice.get("requirement", 0)
    raw_label = str(choice.get("label") or choice.get("text") or choice.get("action") or "")
    raw_l = raw_label.lower()

    if stat == "ITEM":
        return "🎒"

    is_free = (stat in ("NONE", "FREE", "") or req <= 0)
    if is_free:
        if any(k in raw_l for k in ("contract board", "notice board", "bounty board", "bulletin board", "quest board", "bulletin")):
            return "📜"
        if any(k in raw_l for k in ("flirt", "compliment", "praise", "admire", "cherish", "confess", "hug", "kiss", "affection", "fond", "hold hand")):
            return "💖"
        if any(k in raw_l for k in ("joke", "tease", "banter", "laugh", "playful", "ribbing", "witty", "humor", "prank")):
            return "🎭"
        from mechanics.narrative.intent import is_conversational_exit
        if is_conversational_exit(raw_l):
            return "🚪"
        if any(k in raw_l for k in (
            "talk", "speak", "discuss", "ask", "tell", "consult", "comfort", "inquire",
            "reassure", "address", "greet", "converse", "propose", "negotiate", "chat",
            "whisper", "confer", "explain", "advise", "gauge", "interview", "say to", "confront"
        )):
            return "💬"
        if any(k in raw_l for k in (
            "look around", "inspect", "examine", "observe", "scan", "survey", "view the",
            "look at the", "check out the", "read the", "study the", "take in the", "search"
        )):
            return "🔍"
        if any(k in raw_l for k in ("camp", "tent")):
            return "🏕️"
        if any(k in raw_l for k in ("tea", "coffee", "drink", "sip", "tavern", "snack", "eat", "brew", "cup", "ale", "wine", "hearth")):
            return "☕"
        if any(k in raw_l for k in ("rest", "sit", "relax", "breathe", "sleep", "sofa", "bench", "couch", "chair", "nap")):
            return "🛋️"
        if any(k in raw_l for k in ("shelf", "bookshelf", "desk", "drawer", "tinker", "browse", "props", "decor", "cabinet", "paperwork", "documents", "records")):
            return "🖐️"
        if any(k in raw_l for k in ("redress", "get dressed", "don clothes", "put on clothes")):
            return "🥋"
        if any(k in raw_l for k in ("put down", "drop burden", "release hold")):
            return "🤲"
        if any(k in raw_l for k in ("break free", "struggle", "slip out", "wriggle free")):
            return "⛓️"
        if any(k in raw_l for k in ("equipment", "gear", "supplies", "backpack", "pack", "prepare", "sharpen")):
            return "🎒"
        if any(k in raw_l for k in (
            "travel", "head to", "head toward", "depart", "walk to", "walk toward", "exit", "leave",
            "slip out", "make your way", "return to", "step out", "step into", "go to", "move to",
            "journey", "navigate to"
        )) or re.search(r"\b(travel|depart|exit|leave|journey|flee)\b", raw_l):
            return "🚶"
        if any(k in raw_l for k in ("scout", "delve", "forage", "track", "trail", "wilderness", "ruins", "woods", "forest", "patrol")):
            return "🧭"
        return "✨"

    return STAT_EMOJI.get(stat, "❔")

def _get_choice_emoji(choice: dict) -> str:
    """Returns the combined emoji string for an action choice (e.g. '⭐ 🧠' for quest skill check, '🎭 🗣️' for banter check, '🧠' for standard check)."""
    if not isinstance(choice, dict):
        return "✨"
    quest_icon = _get_choice_quest_icon(choice)
    skill_emoji = _get_choice_skill_emoji(choice)

    if quest_icon and skill_emoji and quest_icon != skill_emoji:
        return f"{quest_icon} {skill_emoji}"
    return quest_icon or skill_emoji or "✨"

def _format_items_gained(item_names: list) -> str:
    """Formats a (possibly repeated) list of item names gained in a single
    turn into '{icon} You obtained: X (xN)!' lines -- one per unique item name,
    with duplicates in the list counted as quantity. Returns '' if nothing
    was gained (callers should skip adding the field entirely in that case)."""
    if not item_names:
        return ""
    counts = {}
    order = []
    for name in item_names:
        if name not in counts:
            order.append(name)
        counts[name] = counts.get(name, 0) + 1
    lines = []
    for name in order:
        if "(Lost: Inventory Full!)" in name:
            clean_name = name.replace(" (Lost: Inventory Full!)", "").strip()
            lines.append(f"⚠️ **{clean_name}** could not be carried (Inventory Full!)")
        else:
            icon = get_item_icon(name)
            lines.append(f"{icon} You obtained: **{name}** (x{counts[name]})!")
    return "\n".join(lines)

def _format_items_gained_multi(items_gained_by_user: dict, party: list) -> str:
    """Same as _format_items_gained, but for a multiplayer round -- prefixes
    each character's line(s) with their name so it's clear who got what.
    `party` is a list of (char, inventory) tuples, iterated in turn order."""
    blocks = []
    for char, _ in party:
        names = items_gained_by_user.get(char["user_id"], [])
        lines = _format_items_gained(names)
        if lines:
            blocks.append(f"**{char['name']}**\n{lines}")
    return "\n\n".join(blocks)

def build_outcome_embeds(
    outcome: dict,
    check_field_name: str,
    check_field_value: str,
    loot_text: str,
    result_display: str,
    xp_by_user: dict | None = None,
    session_id: int | None = None,
    primary_tier: str = "success",
) -> list[discord.Embed]:
    """Build the Result embed for both solo/turn-based and sync modes.

    Args:
        outcome:           The raw LLM outcome dict.
        check_field_name:  Name for the check field (e.g. '🎯 Check' / '🎯 Checks').
        check_field_value: Formatted check summary text.
        loot_text:         Pre-formatted loot string (empty string if none).
        result_display:    'detailed' or 'compact'.
        xp_by_user:        Optional {char_name: xp_gained} for Detailed XP display.
        session_id:        Optional session ID to look up story clue progress.
        primary_tier:      The dominant check tier for colour/title selection.
    """
    color = _RESULT_COLORS.get(primary_tier, discord.Color.orange())
    title = _RESULT_TITLES.get(primary_tier, "Result")

    desc = (
        outcome.get("outcome_narrative")
        or outcome.get("narrative")
        or outcome.get("action_outcome")
        or outcome.get("resolution")
        or outcome.get("scene_text")
        or outcome.get("story")
        or outcome.get("description")
        or ""
    ).strip()
    
    if outcome.get("fallback_reason") == "empty_prose":
        desc = "⚠️ *The engine struggled to narrate the outcome. Showing placeholder.* ⚠️\n\n" + desc
        
    story_embed = discord.Embed(
        title=title,
        description=desc,
        color=color,
    )

    # Check summary — always shown
    _safe_add_field(story_embed, name=check_field_name, value=check_field_value, inline=False)
    
    breakdown_embed = discord.Embed(
        title="📊 Action Breakdown & Rewards",
        color=discord.Color.from_str("#2B2D31")
    )

    if result_display == "detailed":
        # ── Unified Combat Log & Vitals Block ──────────────────────────────
        combat_log = outcome.get("_combat_log") or []
        enemy_attack_notice = outcome.get("_enemy_attack_notice")
        char_outcomes = outcome.get("character_outcomes") or []
        npcs_present = outcome.get("npcs_present") or []
        
        summary_lines = []
        if combat_log:
            summary_lines.extend(combat_log)
        elif enemy_attack_notice:
            summary_lines.append(enemy_attack_notice)

        vitals_lines = []
        for co in char_outcomes:
            if not isinstance(co, dict):
                continue
            name = co.get("name", "")
            parts = []
            hp = _safe_int(co.get("hp_change"), default=0)
            mp = _safe_int(co.get("mp_change"), default=0)
            gold = _safe_int(co.get("gold_change"), default=0)
            status_new = [s for s in (co.get("status_effects") or []) if s]
            if hp:
                parts.append(f"{'❤️' if hp < 0 else '💚'} HP {hp:+d}")
            if mp:
                parts.append(f"{'💙' if mp < 0 else '✨'} MP {mp:+d}")
            if gold:
                parts.append(f"💰 Gold {gold:+d}")
            if status_new:
                parts.append(f"⚡ Status: {', '.join(status_new)}")
            xp_gained = (xp_by_user or {}).get(name) or (xp_by_user or {}).get(
                next((k for k in (xp_by_user or {}) if str(k) != name), None), 0
            ) if xp_by_user and len(xp_by_user) == 1 else (xp_by_user or {}).get(name, 0)
            if xp_gained:
                parts.append(f"⭐ XP +{xp_gained}")
            if parts:
                prefix = f"❤️ **{name}**: " if name else ""
                vitals_lines.append(prefix + " | ".join(parts))

        # Include friendly companions in combat vitals
        if combat_log and npcs_present:
            for npc in npcs_present:
                if isinstance(npc, dict) and npc.get("hp") is not None:
                    n_name = npc.get("name", "Companion")
                    n_hp = _safe_int(npc.get("hp"), default=0)
                    n_max = _safe_int(npc.get("max_hp"), default=n_hp)
                    vitals_lines.append(f"❤️ **{n_name}**: 💚 HP {n_hp}/{n_max}")

        if summary_lines or vitals_lines:
            header_title = "⚔️ Combat Summary" if (combat_log or enemy_attack_notice) else "📊 Turn Summary"
            full_block = []
            if summary_lines:
                full_block.extend(summary_lines)
            if vitals_lines:
                if summary_lines:
                    full_block.append("")  # Blank line separator
                full_block.extend(vitals_lines)
            _safe_add_field(breakdown_embed, name=header_title, value="\n".join(full_block), inline=False)

        # ── NPC Relationships, Factions & World Events ─────────────────────
        from namegen import is_valid_entity_name
        social_lines = []
        for rel in (outcome.get("relationship_updates") or []):
            if not isinstance(rel, dict):
                continue
            npc = rel.get("npc_name") or rel.get("name", "")
            if not is_valid_entity_name(npc):
                continue
            delta = int(rel.get("delta_score", 0))
            traits = rel.get("new_traits") or []
            prefs = rel.get("new_preferences") or []
            disc_items = []
            if traits:
                disc_items.extend(traits[:2])
            if prefs:
                disc_items.extend(prefs[:2])
            if rel.get("intimate_revealed"):
                disc_items.append("Intimate Profile")
                rev_attrs = rel.get("revealed_attributes") or []
                if isinstance(rev_attrs, str):
                    rev_attrs = [rev_attrs]
                rev_set = {str(a).lower().strip() for a in rev_attrs if a}
                if rel.get("sensitive_spots_revealed") or rel.get("new_sensitive_spots") or "sensitive_spots" in rev_set:
                    disc_items.append("Sensitive Spots")
                if rel.get("turn_ons_revealed") or rel.get("new_turn_ons") or "turn_ons" in rev_set:
                    disc_items.append("Turn-Ons")
                if rel.get("fetishes_revealed") or rel.get("new_fetishes") or "fetishes" in rev_set:
                    disc_items.append("Fetishes")
                if rel.get("demeanor_revealed") or rel.get("new_demeanor") or "demeanor" in rev_set or "intimate_demeanor" in rev_set:
                    disc_items.append("Intimate Demeanor")
                if rel.get("dynamic_revealed") or rel.get("new_dynamic") or "dynamic" in rev_set or "intimate_dynamic" in rev_set:
                    disc_items.append("Intimate Dynamic")
                if rel.get("intercourse_revealed") or "intercourse" in rev_set:
                    disc_items.append("Intercourse Experience")
                if rel.get("oral_revealed") or "oral" in rev_set:
                    disc_items.append("Oral Experience")
            if npc and (delta or disc_items):
                sign = "+" if delta > 0 else ""
                disc_str = f" [Discovered: {', '.join(disc_items[:3])}]" if disc_items else ""
                social_lines.append(f"🤝 {npc}: {sign}{delta}{disc_str}")
        for fac in (outcome.get("faction_updates") or []):
            if not isinstance(fac, dict):
                continue
            fname = fac.get("faction_name") or fac.get("name", "")
            if not is_valid_entity_name(fname):
                continue
            fdelta = int(fac.get("delta_score", 0))
            if fname and fdelta:
                from cogs.factions import get_faction_emoji
                f_emoji = get_faction_emoji(fname)
                sign = "+" if fdelta > 0 else ""
                social_lines.append(f"{f_emoji} {fname}: {sign}{fdelta} Rep")
        for ev in (outcome.get("world_event_updates") or []):
            if not isinstance(ev, dict):
                continue
            etitle = ev.get("title", "")
            estage = ev.get("stage", "")
            if etitle:
                stage_str = f" → {estage.capitalize()}" if estage else ""
                social_lines.append(f"🌍 {etitle}{stage_str}")
        if social_lines:
            _safe_add_field(breakdown_embed, name="🤝 Social & Faction Updates",
                             value="\n".join(social_lines), inline=False)

        # ── Newly Discovered Factions ─────────────────────────────────
        new_facs = outcome.get("_newly_discovered_factions") or []
        for nf in new_facs:
            if isinstance(nf, dict):
                nf_name = nf.get("name", "")
                nf_hq = nf.get("hq", "")
                from cogs.factions import get_faction_emoji
                emoji = get_faction_emoji(nf_name, template=nf.get("template", ""))
                hq_part = f" | 📍 HQ: **{nf_hq}**" if nf_hq else ""
                _safe_add_field(breakdown_embed, name="✨ Faction Discovered",
                                value=f"{emoji} **{nf_name}**{hq_part}", inline=False)

        # ── Story Clue Discoveries ──────────────────────────────────────
        new_clue = outcome.get("_newly_discovered_clue")
        if new_clue:
            _safe_add_field(breakdown_embed, name="🔍 Story Discovery",
                             value=f"🔍 **New Investigation Note:** *{new_clue}*", inline=False)
    else:
        # Compact mode fallback for combat summary
        combat_log = outcome.get("_combat_log") or []
        enemy_attack_notice = outcome.get("_enemy_attack_notice")
        if combat_log:
            _safe_add_field(breakdown_embed, name="⚔️ Combat Summary", value="\n".join(combat_log), inline=False)
        elif enemy_attack_notice:
            _safe_add_field(breakdown_embed, name="⚔️ Combat Summary", value=enemy_attack_notice, inline=False)

    # ── Combat Resolution — victory / defeat notices ───────────────────────
    combat_notice = outcome.get("_combat_resolved_notice")
    if combat_notice:
        _safe_add_field(breakdown_embed, name="⚔️ Combat Resolved", value=str(combat_notice).replace("\\n", "\n"), inline=False)
        
    defeat_notice = outcome.get("_party_defeated_notice")
    if defeat_notice:
        _safe_add_field(breakdown_embed, name="💀 Party Defeated", value=str(defeat_notice).replace("\\n", "\n"), inline=False)

    # ── Loot — always shown ────────────────────────────────────────────────
    if loot_text:
        _safe_add_field(breakdown_embed, name="🎒 Loot", value=loot_text, inline=False)

    # ── Quest completion notice(s) — shown for every completed quest ──────────
    rn_list = outcome.get("_quest_reward_notices") or []
    for rn in rn_list:
        if not rn or not rn.get("claimed"):
            continue
        reward_parts = []
        if rn.get("xp"): reward_parts.append(f"+{rn['xp']} XP")
        if rn.get("gold"): reward_parts.append(f"+{rn['gold']} Gold")
        rew_str = ", ".join(reward_parts) or "Claimed"
        _safe_add_field(
            breakdown_embed,
            name=f"🎉 Quest Completed: {rn.get('title')}",
            value=f"**Rewards:** {rew_str}",
            inline=False,
        )

    # ── Sub-Quest completion notice(s) ────────────────────────────────────────
    completed_sqs = outcome.get("_completed_sub_quests") or []
    for sq_info in completed_sqs:
        arch = f" [{sq_info['archetype']}]" if sq_info.get("archetype") else ""
        _safe_add_field(
            breakdown_embed,
            name=f"☑️ Sub-Quest Completed",
            value=f"{arch} **{sq_info.get('text', '')}**",
            inline=False
        )

    # ── Waypoint Progression notice(s) ────────────────────────────────────────
    wp_notices = outcome.get("_waypoint_notices") or []
    for wp in wp_notices:
        trigger = wp.get("trigger")
        if trigger == "arrival":
            icon = "📌"
            action = "Reached Destination"
        elif trigger == "skill_check":
            icon = "🎯"
            action = "Objective Completed"
        elif trigger == "resource_progress":
            icon = "📦"
            action = "Resources Gathered"
        else:
            icon = "▶️"
            action = "Stage Progress"
            
        stage_completed = wp.get("stage_completed")
        stage_label = wp.get("stage_label", "")
        next_wp = wp.get("next_waypoint")
        quest_complete = wp.get("all_stages_complete")
        
        lines = []
        if stage_completed is not None:
            lines.append(f"**{action}:** {stage_label}")
        if trigger == "resource_progress" or (trigger == "skill_check" and wp.get("resource_target")):
            lines.append(f"**Progress:** {wp.get('resource_collected', 0)} / {wp.get('resource_target', 0)}")
            
        if not quest_complete and next_wp:
            lines.append(f"**Next:** {next_wp.get('stage_label', 'Continue quest')}")
        elif quest_complete:
            lines.append("**Status:** Waypoint chain completed!")
            
        qid = wp.get("quest_id")
        quest_label = ""
        if qid and session_id:
            try:
                q = db.get_quest_by_id(session_id, qid)
                if q:
                    if q.get("is_story_quest"):
                        quest_label = "Story Quest"
                    else:
                        quest_label = q.get("title", "Bounty")[:30]
            except Exception:
                pass

        header_title = f"{icon} {quest_label} Waypoint" if quest_label else f"{icon} Waypoint Updated"
        _safe_add_field(
            breakdown_embed,
            name=header_title,
            value="\n".join(lines),
            inline=False
        )

    if len(breakdown_embed.fields) > 0:
        return [story_embed, breakdown_embed]
        
    return [story_embed]

def _tracker_header(emoji: str, singular: str, plural: str, count: int) -> str:
    """Builds a tracker field header that reads correctly whether there's
    exactly one entity or several, e.g. '🧑\u200d🤝\u200d🧑 Character' vs
    '🧑\u200d🤝\u200d🧑 Characters'. The emoji always stays attached to
    whichever form is chosen."""
    return f"{emoji} {singular if count == 1 else plural}"

def _truncate_embed_text(text: str, max_len: int = 4000) -> str:
    if not text or len(text) <= max_len:
        return text or ""
    truncated = text[:max_len]
    last_period = truncated.rfind('.')
    if last_period > max_len * 0.8:
        return truncated[:last_period + 1] + "\n\n*(Text truncated to fit Discord limits)*"
    return truncated.rsplit(' ', 1)[0] + "...\n\n*(Text truncated to fit Discord limits)*"

def scene_embed(session: dict, actor_char: dict, scene_title: str, narrative: str,
                 choices: list, image_url: str | None = None) -> list[discord.Embed]:
    story_embed = discord.Embed(title=_truncate_field_name(scene_title or "Hikayat", 256), description=_truncate_embed_text(narrative),
                           color=discord.Color.dark_gold())
    if image_url:
        story_embed.set_image(url=image_url)

    dash_embed = discord.Embed(title="⚙️ Game Dashboard", color=discord.Color.gold())
    _safe_add_field(dash_embed, name="📍 Location", value=_location_text(session, char_name=actor_char.get("name", "")), inline=False)
    
    from mechanics.system.time_engine import format_time_header
    c_day = session.get("current_day") or 1
    c_min = session.get("current_minute") if session.get("current_minute") is not None else 480
    _safe_add_field(dash_embed, name="📅 Time & Day", value=format_time_header(c_day, c_min), inline=False)

    enemies = session.get("nearby_enemies", [])
    enemy_names = {game_engine._get_npc_name(e).lower() for e in enemies if e}

    raw_npcs = session.get("current_npcs") or []
    party_char_names = set()
    if actor_char and actor_char.get("name"):
        party_char_names.add(str(actor_char["name"]).strip().lower())
    if session.get("turn_order"):
        for uid in session["turn_order"]:
            try:
                with db.get_conn() as conn:
                    c_rows = conn.execute("SELECT name FROM characters WHERE user_id = ?", (uid,)).fetchall()
                    for cr in c_rows:
                        if cr["name"]:
                            party_char_names.add(str(cr["name"]).strip().lower())
            except Exception:
                pass

    npcs = [
        n for n in raw_npcs
        if game_engine._get_npc_name(n).lower() not in enemy_names
        and game_engine._get_npc_name(n).lower() not in party_char_names
    ]
    scen_key = session.get("scenario", "fantasy")
    from scenario_data import is_mechanic_enabled
    combat_enabled = is_mechanic_enabled(scen_key, "tactical_combat")

    if npcs:
        from mechanics.world.mobility import get_session_dialogue_partners
        dialogue_partners = get_session_dialogue_partners(session)
        _safe_add_field(dash_embed, name=_tracker_header("🧑‍🤝‍🧑", "Character", "Characters", len(npcs)),
                         value=_tracker_group_text(npcs, dialogue_partners=dialogue_partners, show_vitals=combat_enabled), inline=False)

    if enemies:
        _safe_add_field(dash_embed, name=_tracker_header("👹", "Enemy", "Enemies", len(enemies)),
                         value=_tracker_group_text(enemies, show_vitals=combat_enabled), inline=False)

    if combat_enabled:
        vitals_header = _tracker_header("📊", "Party", "Party", 1)
    else:
        vitals_header = _tracker_header("📊", "Player", "Players", len(session.get("turn_order", [])))
    _safe_add_field(dash_embed, name=vitals_header,
                     value=_party_vitals_text(session), inline=False)

    return [story_embed, dash_embed]

def sync_scene_embed(session: dict, party: list, scene_title: str, narrative: str,
                      choices: list, waiting_on: list, image_url: str | None = None) -> list[discord.Embed]:
    story_embed = discord.Embed(title=_truncate_field_name(scene_title or "Hikayat", 256), description=_truncate_embed_text(narrative),
                           color=discord.Color.dark_teal())
    if image_url:
        story_embed.set_image(url=image_url)

    first_p = party[0][0] if (party and isinstance(party[0], (tuple, list)) and party[0]) else (party[0] if party else None)
    first_char_name = first_p.get("name", "") if isinstance(first_p, dict) else ""
    dash_embed = discord.Embed(title="⚙️ Game Dashboard", color=discord.Color.teal())
    _safe_add_field(dash_embed, name="📍 Location", value=_location_text(session, char_name=first_char_name), inline=False)

    enemies = session.get("nearby_enemies", [])
    enemy_names = {game_engine._get_npc_name(e).lower() for e in enemies if e}

    party_char_names = set()
    if party:
        for p in party:
            p_char = p[0] if (isinstance(p, (tuple, list)) and p) else p
            if isinstance(p_char, dict) and p_char.get("name"):
                party_char_names.add(str(p_char["name"]).strip().lower())
    if session.get("turn_order"):
        for uid in session["turn_order"]:
            try:
                with db.get_conn() as conn:
                    c_rows = conn.execute("SELECT name FROM characters WHERE user_id = ?", (uid,)).fetchall()
                    for cr in c_rows:
                        if cr["name"]:
                            party_char_names.add(str(cr["name"]).strip().lower())
            except Exception:
                pass

    raw_npcs = session.get("current_npcs") or []
    npcs = [
        n for n in raw_npcs
        if game_engine._get_npc_name(n).lower() not in enemy_names
        and game_engine._get_npc_name(n).lower() not in party_char_names
    ]
    scen_key = session.get("scenario", "fantasy")
    from scenario_data import is_mechanic_enabled
    combat_enabled = is_mechanic_enabled(scen_key, "tactical_combat")

    if npcs:
        from mechanics.world.mobility import get_session_dialogue_partners
        dialogue_partners = get_session_dialogue_partners(session)
        _safe_add_field(dash_embed, name=_tracker_header("🧑‍🤝‍🧑", "Character", "Characters", len(npcs)),
                         value=_tracker_group_text(npcs, dialogue_partners=dialogue_partners, show_vitals=combat_enabled), inline=False)

    if enemies:
        _safe_add_field(dash_embed, name=_tracker_header("👹", "Enemy", "Enemies", len(enemies)),
                         value=_tracker_group_text(enemies, show_vitals=combat_enabled), inline=False)

    if combat_enabled:
        vitals_header = _tracker_header("📊", "Party", "Party", 1)
    else:
        vitals_header = _tracker_header("📊", "Player", "Players", len(session.get("turn_order", [])))
    _safe_add_field(dash_embed, name=vitals_header,
                     value=_party_vitals_text(session), inline=False)

    if waiting_on:
        mentions = ", ".join(f"<@{uid}>" for uid in waiting_on)
        _safe_add_field(dash_embed, name="⏳ Waiting on", value=mentions, inline=False)
        
    return [story_embed, dash_embed]

def _choice_button_label(idx: int, choice: dict, prefix: str, show_percentages: bool = True) -> str:
    """Builds a button label keeping the whole label within Discord's 80-character limit."""
    label_text = _strip_leading_emojis(choice.get("label", ""))
    if "%" in label_text:
        full_text = label_text.strip()
        first_char = full_text[0] if full_text else ""
        if ord(first_char) > 255:
            full_text = full_text[1:].strip()
        if not show_percentages:
            import re
            full_text = re.sub(r'\b\d+%\s*', '', full_text).strip()
        return full_text[:80]

    head = f"{prefix}" if show_percentages else ""
    budget = 80 - len(head)
    if len(label_text) > budget:
        label_text = label_text[:max(0, budget - 1)].rstrip() + "…"
    return f"{head}{label_text}"

def build_world_map_embed(session_id: int, scen_key: str, current_loc: str = "", char_name: str = "", zones: list = None) -> discord.Embed:
    """Builds the rich World Map Atlas embed summarizing all discovered Tier 1 Zones."""
    if zones is None:
        from mechanics.world.locations import get_zone_summary_tree
        zones = get_zone_summary_tree(session_id, scen_key, current_loc=current_loc, char_name=char_name)
    embed = discord.Embed(
        title="🗺️ World Map — Discovered Regions",
        description="Select a region from the dropdown below to explore its local places or travel across districts:",
        color=discord.Color.gold()
    )
    for z in zones[:25]:
        z_name = z["zone_name"]
        z_emoji = z.get("emoji", "📍")
        curr_badge = " `[Current Region]`" if z.get("is_current") else ""
        header = f"{'🧭 ' if z.get('is_current') else z_emoji + ' '}{z_name}{curr_badge}"
        lines = []
        theme_tag = z.get("theme")
        if theme_tag:
            lines.append(f"• **Type:** {theme_tag}")
        lines.append(f"• **Known Places:** {z.get('places_count', 0)} discovered")
        if z.get("active_tags"):
            lines.append(f"• **Highlights:** {' | '.join(z['active_tags'])}")
        _safe_add_field(embed, name=header, value="\n".join(lines) if lines else "—", inline=False)
    return embed

def build_zone_places_embed(session_id: int, zone_name: str, scen_key: str, current_loc: str = "", char_name: str = "") -> discord.Embed:
    """Builds the regional places embed showing places within a selected zone."""
    from mechanics.world.locations import get_zone_summary_tree, get_zone_emoji
    zones = get_zone_summary_tree(session_id, scen_key, current_loc=current_loc, char_name=char_name)
    target_zone = next((z for z in zones if z["zone_name"].lower() == zone_name.lower()), None)
    z_emoji = target_zone.get("emoji", get_zone_emoji(zone_name, scen_key)) if target_zone else get_zone_emoji(zone_name, scen_key)

    embed = discord.Embed(
        title=f"{z_emoji} Region: {zone_name}",
        color=discord.Color.gold()
    )
    if target_zone and target_zone.get("theme"):
        embed.description = f"**{target_zone['theme']}**\n\nSelect a destination within this region:"
    else:
        embed.description = "Select a destination within this region:"

    if target_zone and target_zone.get("active_tags"):
        _safe_add_field(embed, name="🏷️ Regional Highlights", value=" | ".join(target_zone["active_tags"]), inline=False)

    if target_zone:
        places = target_zone.get("primary_locations", [])
        if places:
            place_lines = []
            for p in places[:15]:
                arch_emoji = p.get("archetype_emoji") or p.get("emoji") or "📍"
                badges = p.get("badges", "")
                badge_str = f" {badges}" if badges else ""
                place_lines.append(f"• {arch_emoji} **{p['name']}**{badge_str}")
            _safe_add_field(embed, name="📍 Discovered Locations", value="\n".join(place_lines), inline=False)
    return embed

def _get_quest_scenario_labels(scen_key: str = None) -> dict:
    """Returns scenario-adaptive terminology and emojis for the Quest UI tabs and notice boards."""
    from mechanics.world.locations import is_school_scenario
    scen = str(scen_key or "").lower()
    if is_school_scenario(scen):
        return {
            "main_tab": "Story Chapter",
            "main_emoji": "⭐",
            "bounties_tab": "Campus Favors",
            "bounties_emoji": "🎯",
            "board_label": "Campus Bulletin",
            "board_emoji": "📋"
        }
    if "cyberpunk" in scen or "sci_fi" in scen or "space" in scen:
        return {
            "main_tab": "Main Op",
            "main_emoji": "⭐",
            "bounties_tab": "Contracts",
            "bounties_emoji": "🎯",
            "board_label": "Terminal Postings",
            "board_emoji": "💾"
        }
    if "apocalypse" in scen:
        return {
            "main_tab": "Main Mission",
            "main_emoji": "⭐",
            "bounties_tab": "Dispatches",
            "bounties_emoji": "🎯",
            "board_label": "Radio Dispatch",
            "board_emoji": "📻"
        }
    return {
        "main_tab": "Main Quest",
        "main_emoji": "⭐",
        "bounties_tab": "Bounties",
        "bounties_emoji": "🎯",
        "board_label": "Notice Board",
        "board_emoji": "📋"
    }

def _build_campaign_goals_embed(session_id: int) -> discord.Embed:
    goals = db.get_session_campaign_goals(session_id)
    cur_ch = db.get_session_chapter(session_id) or 1
    embed = discord.Embed(
        title="🏆 Campaign End Goals",
        description=f"Current Progress: **Chapter {cur_ch} of 10**\nLong-term campaign objectives tracking overall story progression.",
        color=discord.Color.gold()
    )
    if not goals:
        embed.add_field(name="No Campaign Goals", value="No long-term campaign goals are currently active.", inline=False)
        return embed

    for g in goals:
        pct = g.get("progress_pct", 0)
        bar = "█" * (pct // 10) + "░" * (10 - (pct // 10))
        status_icon = "🏆" if pct >= 100 else ("🎯" if pct > 0 else "📌")
        embed.add_field(
            name=f"{status_icon} {g['title']} [{bar}] {pct}%",
            value=f"*{g.get('description', '')}*",
            inline=False
        )
    return embed

def _build_main_quest_embed(session_id: int) -> discord.Embed:
    session = db.get_session(session_id)
    scen_key = session.get("scenario", "fantasy") if session else "fantasy"
    labels = _get_quest_scenario_labels(scen_key)
    active_sq = db.get_active_story_quest(session_id)

    if not active_sq:
        embed = discord.Embed(
            title=f"{labels['main_emoji']} {labels['main_tab']} — No Active Objective",
            description="You currently have no active main story chapter. Explore the world, interact with key characters, or check local notice boards to unlock the next chapter!",
            color=discord.Color.blue()
        )
        embed.add_field(
            name="Exploration Guidance",
            value="Use **/adventure resume** to continue your current journey or visit points of interest on the world map.",
            inline=False
        )
        return embed

    title = active_sq.get("title", "Active Chapter")
    q_type = active_sq.get("quest_type", "Story Quest")
    obj = active_sq.get("objective", "")
    sub_objs = active_sq.get("sub_objectives", []) or []
    all_so_done = bool(sub_objs and all(isinstance(so, dict) and so.get("completed") for so in sub_objs))

    if all_so_done:
        embed = discord.Embed(
            title=f"⚡ {labels['main_tab'].upper()} (CLIMAX READY): {title}",
            description=f"**Objective:** {obj}",
            color=discord.Color.purple()
        )
    else:
        embed = discord.Embed(
            title=f"⭐ {labels['main_tab'].upper()}: {title}",
            description=f"**Objective:** {obj}",
            color=discord.Color.blue()
        )

    # Waypoint / Stage Compass Quick-Tracker for in-progress stage
    active_wp_lead = None
    if sub_objs and not all_so_done:
        for so in sub_objs:
            if not so.get("completed") and so.get("id"):
                try:
                    wp = db.get_active_waypoint(session_id, active_sq.get("quest_id"), so["id"])
                    if wp and wp.get("target_location"):
                        active_wp_lead = wp
                        break
                except Exception:
                    pass

    if active_wp_lead:
        s_idx = active_wp_lead.get("stage_index", 1)
        s_lbl = active_wp_lead.get("stage_label", "")
        s_loc = active_wp_lead.get("target_location", "")
        embed.add_field(
            name="📍 Current Waypoint Lead",
            value=f"**Stage {s_idx}/3:** *{s_lbl}*\n➔ 📍 **Target Location:** `{s_loc}`",
            inline=False
        )

    # Sub-Objectives Checklist
    if sub_objs:
        sub_lines = []
        for so in sub_objs:
            is_done = bool(so.get("completed"))
            chk = "☑️" if is_done else "☐"
            arch = f" [{so['archetype']}]" if so.get("archetype") else ""
            raw_text = str(so.get("text", "")).strip()
            if len(raw_text) > 175:
                raw_text = raw_text[:172].rstrip() + "..."
            line = f"{chk}{arch} {raw_text}"
            if not is_done and so.get("id"):
                try:
                    wp = db.get_active_waypoint(session_id, active_sq.get("quest_id"), so["id"])
                    if wp:
                        s_idx = wp.get("stage_index", 1)
                        s_lbl = wp.get("stage_label", "")
                        s_loc = wp.get("target_location", "")
                        loc_display = f" ➔ 📍 `{s_loc}`" if s_loc else ""
                        line += f"\n   ↳ *Stage {s_idx}/3: {s_lbl}{loc_display}*"
                except Exception:
                    pass
            sub_lines.append(line)
        
        sub_val = "\n".join(sub_lines)
        if all_so_done:
            from mechanics.world.waypoints import get_story_quest_climax_location
            _, climax_loc = get_story_quest_climax_location(session_id)
            climax_display = f"`{climax_loc}`" if climax_loc else "`Local Area`"
            sub_val += (
                f"\n\n⚡ **CLIMAX READY — FINAL SHOWDOWN:**\n"
                f"• All preliminary sub-objectives completed!\n"
                f"• 📍 **Destination:** {climax_display}\n"
                f"• *Proceed to the destination to confront the climax encounter and conclude this chapter!*"
            )
        embed.add_field(name="Sub-Objectives (Tackle in any order)", value=sub_val[:1024], inline=False)

    # Streamlined Investigation Notes / Clues Dossier
    clues_str = active_sq.get("current_clues") or ""
    parsed_clues = game_engine.parse_clue_list(clues_str)
    if not parsed_clues:
        cur_ch = db.get_session_chapter(session_id) or 1
        ch_clues = db.get_session_clues(session_id, chapter=cur_ch)
        if ch_clues:
            parsed_clues = [f"{c.get('title', 'Lead')}: {c.get('lead_text', '')}" for c in ch_clues]
    if parsed_clues:
        clue_lines = "\n".join(f"**{i}.** {c}" for i, c in enumerate(parsed_clues, 1))
        embed.add_field(
            name=f"🔍 Investigation Notes ({len(parsed_clues)} Discovered)",
            value=clue_lines[:1024],
            inline=False
        )
    else:
        embed.add_field(
            name="🔍 Investigation Notes",
            value="*No clues discovered for this chapter yet. Search locations and converse with contacts to uncover leads.*",
            inline=False
        )

    # Rewards
    rxp = active_sq.get("reward_xp", 100)
    rgold = active_sq.get("reward_gold", 25)
    ritem = active_sq.get("reward_item", "")
    rewards = []
    if rxp: rewards.append(f"{rxp} XP")
    if rgold: rewards.append(f"{rgold} Gold")
    if ritem: rewards.append(f"🎒 Item: {ritem}")
    embed.add_field(name="Rewards", value=", ".join(rewards) if rewards else "Standard", inline=False)

    return embed

def _build_bounties_embed(session_id: int, selected_quest_id: str | None = None) -> discord.Embed:
    session = db.get_session(session_id)
    scen_key = session.get("scenario", "fantasy") if session else "fantasy"
    cur_loc = session.get("current_location", "") if session else ""
    labels = _get_quest_scenario_labels(scen_key)

    all_active = db.get_session_quests(session_id, status="Active")
    active_bounties = [
        q for q in all_active
        if not (q.get("is_story_quest") or q.get("quest_type") in ("Story Quest", "Main Quest"))
        and q.get("title") and q["title"] not in ("Active Objective", "Complete objective.", "")
    ]
    seen = set()
    deduped = []
    for b in active_bounties:
        qid = b.get("quest_id") or b.get("title")
        if qid not in seen:
            seen.add(qid)
            deduped.append(b)
    active_bounties = deduped

    # Detailed Inspector Mode
    if selected_quest_id:
        target_bounty = next((b for b in active_bounties if b.get("quest_id") == selected_quest_id), None)
        if not target_bounty:
            target_bounty = db.get_quest_by_id(session_id, selected_quest_id)

        if target_bounty:
            b_id = target_bounty.get("quest_id", "")
            title = target_bounty.get("title", "Bounty Details")
            q_type = target_bounty.get("quest_type", "Side Bounty")
            icon = _quest_type_icon(q_type)
            obj = target_bounty.get("objective", "")
            clues = target_bounty.get("current_clues", "")

            wps = db.get_quest_waypoints(session_id, b_id, sub_obj_id=None)
            active_wp = db.get_active_waypoint(session_id, b_id, sub_obj_id=None)

            embed = discord.Embed(
                title=f"{icon} {labels['bounties_tab']} Detail: {title}",
                description=f"**Type:** {q_type}\n**Status:** ⏳ In Progress\n\n**Objective:**\n{obj}",
                color=discord.Color.teal()
            )

            # 1. Progression Roadmap & Stage Checklist
            if wps:
                completed_count = len([w for w in wps if w.get("status") == "completed"])
                total_stages = len(wps)
                pct = int((completed_count / total_stages) * 100) if total_stages > 0 else 0
                bar = "█" * (pct // 10) + "░" * (10 - (pct // 10))
                cur_stage_idx = active_wp.get("stage_index", total_stages) if active_wp else total_stages

                stage_lines = []
                for wp in wps:
                    st_idx = wp.get("stage_index", 1)
                    st_status = wp.get("status", "locked")
                    st_lbl = wp.get("stage_label", "")
                    st_loc = wp.get("target_location", "")
                    st_npc = wp.get("target_npc", "")

                    if st_status == "completed":
                        chk = "☑️"
                        status_str = "Completed"
                        stage_lines.append(f"{chk} **Stage {st_idx} ({status_str}):** *{st_lbl}*")
                    elif st_status == "active":
                        chk = "📍"
                        status_str = "Active Lead"
                        loc_display = f"\n   ↳ 📍 **Target Location:** `{st_loc}`" if st_loc else ""
                        npc_display = f"\n   ↳ 👤 **Contact / NPC:** `{st_npc}`" if st_npc else ""

                        # Check gathering resource target
                        res_tgt = wp.get("resource_target", 0)
                        res_col = wp.get("resource_collected", 0)
                        res_display = ""
                        if res_tgt > 0:
                            res_pct = int(min(1.0, res_col / res_tgt) * 10)
                            res_bar = "█" * res_pct + "░" * (10 - res_pct)
                            res_display = f"\n   ↳ 📦 **Gathering Progress:** `{res_col}/{res_tgt}` [{res_bar}]"

                        stage_lines.append(f"{chk} **Stage {st_idx} ({status_str}):** *{st_lbl}*{loc_display}{npc_display}{res_display}")
                    else:
                        chk = "🔒"
                        status_str = "Locked"
                        stage_lines.append(f"{chk} **Stage {st_idx} ({status_str}):** *{st_lbl}*")

                header_text = f"[{bar}] Stage {cur_stage_idx} of {total_stages} ({pct}%)"
                embed.add_field(
                    name="📊 Progression Roadmap",
                    value=f"**Milestone Progress:** `{header_text}`\n\n" + "\n".join(stage_lines),
                    inline=False
                )
            else:
                raw_prog = target_bounty.get("progress") or "In Progress"
                embed.add_field(name="📊 Progression Status", value=f"**Status:** `{raw_prog}`", inline=False)

            # 2. Active Action Callout Box
            if active_wp:
                action_lines = [f"**Current Task:** {active_wp.get('stage_label', '')}"]
                if active_wp.get("target_location"):
                    action_lines.append(f"📍 **Destination:** `{active_wp['target_location']}`")
                if active_wp.get("target_npc"):
                    action_lines.append(f"👤 **Key Contact:** `{active_wp['target_npc']}`")
                trig = active_wp.get("completion_trigger", "arrival")
                trig_str = "Travel to destination" if trig == "arrival" else "Pass thematic skill check / investigation"
                action_lines.append(f"🎲 **Requirement:** *{trig_str}*")
                embed.add_field(name="🎯 Current Milestone Action", value="\n".join(action_lines), inline=False)

            # 3. Contract Intel & Clues
            if clues:
                embed.add_field(name="🔍 Bounty Intel & Notes", value=clues[:1024], inline=False)

            # 4. Rewards
            rxp = target_bounty.get("reward_xp", 100)
            rgold = target_bounty.get("reward_gold", 25)
            ritem = target_bounty.get("reward_item", "")
            rewards = []
            if rxp: rewards.append(f"{rxp} XP")
            if rgold: rewards.append(f"{rgold} Gold")
            if ritem: rewards.append(f"🎒 Item: {ritem}")
            embed.add_field(name="Contract Rewards", value=", ".join(rewards) if rewards else "Standard", inline=False)
            return embed

    # Summary Overview Mode
    embed = discord.Embed(
        title=f"{labels['bounties_emoji']} {labels['bounties_tab']} ({len(active_bounties)} Active)",
        description="Select a contract from the dropdown menu below to inspect detailed progression, waypoints, or manage the bounty.",
        color=discord.Color.teal()
    )

    if not active_bounties:
        from mechanics.world.locations import location_has_bounty_board
        has_board = location_has_bounty_board(cur_loc, scen_key=scen_key)
        if has_board:
            embed.description = (
                "You currently have no active side bounties in your log.\n\n"
                f"📋 **{labels['board_label']} Available Here!**\n"
                f"Click the **{labels['board_label']}** button below to accept new postings!"
            )
        else:
            embed.description = (
                "You currently have no active side bounties in your log.\n\n"
                "Visit a local Guild Hall, Campus Bulletin, Tavern, or Hub to accept new commissions."
            )
        embed.add_field(name="Empty Contract Log", value="Accept commissions from notice boards across the world.", inline=False)
        return embed

    for idx, b in enumerate(active_bounties[:5], start=1):
        q_type = b.get("quest_type", "Side Bounty")
        icon = _quest_type_icon(q_type)
        obj = b.get("objective", "")
        if len(obj) > 200:
            obj = obj[:197].rstrip() + "..."

        embed.add_field(
            name=f"{idx}. {icon} {b['title']} [{q_type}]",
            value=f"**Objective:** {obj}",
            inline=False
        )

    return embed

def _build_history_embed(session_id: int, selected_quest_id: str | None = None) -> discord.Embed:
    all_quests = db.get_session_quests(session_id)
    history_quests = [
        q for q in all_quests
        if q.get("status") in ("Completed", "Failed", "Abandoned")
        and q.get("title") and q["title"] not in ("Active Objective", "Complete objective.", "")
    ]
    seen = set()
    deduped = []
    for q in history_quests:
        qid = q.get("quest_id") or q.get("title")
        if qid not in seen:
            seen.add(qid)
            deduped.append(q)
    history_quests = deduped

    # Detailed Inspector Mode for a specific past quest
    if selected_quest_id:
        target_q = next((q for q in history_quests if q.get("quest_id") == selected_quest_id), None)
        if not target_q:
            target_q = db.get_quest_by_id(session_id, selected_quest_id)

        if target_q:
            title = target_q.get("title", "Past Quest Record")
            status = target_q.get("status", "Completed")
            is_sq = bool(target_q.get("is_story_quest") or target_q.get("quest_type") in ("Story Quest", "Main Quest"))
            icon = "⭐" if is_sq else _quest_type_icon(target_q.get("quest_type"))
            badge = "✅ Completed" if status == "Completed" else ("🛑 Failed" if status == "Failed" else "⏸️ Abandoned")

            embed = discord.Embed(
                title=f"{icon} Historical Record: {title}",
                description=f"**Type:** {'Story Chapter' if is_sq else target_q.get('quest_type', 'Side Bounty')}\n**Outcome:** {badge}\n\n**Objective:**\n{target_q.get('objective', '')}",
                color=discord.Color.gold() if status == "Completed" else discord.Color.dark_grey()
            )

            if is_sq:
                sub_objs = target_q.get("sub_objectives", []) or []
                if sub_objs:
                    sub_lines = []
                    for so in sub_objs:
                        chk = "☑️" if so.get("completed") else "☐"
                        arch = f" [{so['archetype']}]" if so.get("archetype") else ""
                        sub_lines.append(f"{chk}{arch} {so.get('text', '')}")
                    embed.add_field(name="Sub-Objectives Record", value="\n".join(sub_lines)[:1024], inline=False)

            rxp = target_q.get("reward_xp", 100)
            rgold = target_q.get("reward_gold", 25)
            ritem = target_q.get("reward_item", "")
            rewards = []
            if rxp: rewards.append(f"{rxp} XP")
            if rgold: rewards.append(f"{rgold} Gold")
            if ritem: rewards.append(f"🎒 Item: {ritem}")
            embed.add_field(name="Rewards Earned", value=", ".join(rewards) if rewards else "Standard", inline=False)
            return embed

    # Summary Overview Mode
    completed_sq = [q for q in history_quests if (q.get("is_story_quest") or q.get("quest_type") in ("Story Quest", "Main Quest")) and q.get("status") == "Completed"]
    completed_bnt = [q for q in history_quests if not (q.get("is_story_quest") or q.get("quest_type") in ("Story Quest", "Main Quest")) and q.get("status") == "Completed"]
    total_xp = sum(q.get("reward_xp", 0) for q in history_quests if q.get("status") == "Completed")
    total_gold = sum(q.get("reward_gold", 0) for q in history_quests if q.get("status") == "Completed")

    embed = discord.Embed(
        title="📜 Quest Log — History & Archive",
        description=(
            f"📊 **Career Record:** `{len(completed_sq)}` Chapters Completed • `{len(completed_bnt)}` Bounties Finished\n"
            f"💰 **Total Rewards Earned:** `+{total_xp:,} XP` • `+{total_gold:,} Gold`\n\n"
            "*Select an archived quest from the dropdown below to inspect full records and past sub-objectives.*"
        ),
        color=discord.Color.gold()
    )

    if not history_quests:
        embed.add_field(name="No Past Records", value="No completed or archived quests found in your history log yet.", inline=False)
        return embed

    history_lines = []
    for q in history_quests[:12]:
        status = q.get("status", "Completed")
        badge = "✅" if status == "Completed" else ("🛑" if status == "Failed" else "⏸️")
        is_sq = bool(q.get("is_story_quest") or q.get("quest_type") in ("Story Quest", "Main Quest"))
        q_label = "Story Quest" if is_sq else q.get("quest_type", "Side Bounty")
        icon = "⭐" if is_sq else _quest_type_icon(q.get("quest_type"))
        history_lines.append(f"• {badge} {icon} **{q['title']}** *({q_label})*")

    embed.add_field(
        name=f"Archived Quests ({len(history_quests)} Total)",
        value="\n".join(history_lines)[:1024],
        inline=False
    )

    return embed

def _build_caseboard_embed(session_id: int, selected_suspect: str | None = None) -> discord.Embed:
    all_clues = db.get_session_clues(session_id)
    if not all_clues:
        all_clues = db.get_session_clues(session_id)

    cur_ch = db.get_session_chapter(session_id) or 1
    suspect_filter = None if selected_suspect in (None, "__all__", "") else selected_suspect
    clues = [c for c in all_clues if not suspect_filter or (c.get("linked_npc") and suspect_filter.lower() in c["linked_npc"].lower())]

    embed = discord.Embed(
        title="🗂️ Campaign Investigation Caseboard",
        description=(
            f"Campaign Dossier — **Chapter {cur_ch} of 10** • Total Evidence: `{len(all_clues)}` Leads\n"
            + (f"🔍 *Filtered by suspect:* **{suspect_filter}**\n" if suspect_filter else "*All verified findings, witness testimonies, and physical traces recorded across all chapters.*\n")
        ),
        color=discord.Color.dark_teal()
    )

    if not clues:
        embed.add_field(
            name="Empty Case File",
            value="*No evidence recorded yet. Complete investigation waypoints, uncover phone rumors, or question local contacts to log leads!*",
            inline=False
        )
        return embed

    deductions = [c for c in clues if c.get("category") == "deduction"]
    if deductions:
        ded_lines = [f"⚡ **{d['title']}**\n*{d['lead_text']}*" for d in deductions[:4]]
        embed.add_field(
            name=f"⚡ Breakthrough Deductions ({len(deductions)})",
            value="\n\n".join(ded_lines)[:1024],
            inline=False
        )

    categories = [
        ("physical", "🔍 Physical Evidence"),
        ("testimonial", "🗣️ Witness Testimony"),
        ("digital", "💾 Digital & Phone Records"),
        ("document", "📄 Documents & Files")
    ]

    for cat_key, cat_label in categories:
        cat_clues = [c for c in clues if c.get("category") == cat_key]
        if cat_clues:
            lines = []
            for c in cat_clues[:5]:
                if c.get("is_consumed"):
                    status_icon = "🔗 [Used]"
                elif c.get("is_verified"):
                    status_icon = "✅ [Verified]"
                else:
                    status_icon = "⏳ [Open Lead]"
                loc_str = f"📍 {c['source_location']}" if c.get("source_location") else "📍 Unspecified"
                npc_str = f" • 👤 {c['linked_npc']}" if c.get("linked_npc") else ""
                lines.append(
                    f"{status_icon} **{c['title']}**\n"
                    f"*{c['lead_text'][:120]}*\n"
                    f"↳ `{loc_str}`{npc_str} `[Ch. {c.get('chapter', 1)}]`"
                )
            embed.add_field(
                name=f"{cat_label} ({len(cat_clues)})",
                value="\n".join(lines)[:1024],
                inline=False
            )

    return embed

def _build_quest_log_embed(session_id: int, tab: str = "Main Quest", selected_quest_id: str | None = None, selected_suspect: str | None = None) -> discord.Embed:
    if tab in ("Main Quest", "Active", "Notes"):
        return _build_main_quest_embed(session_id)
    elif tab in ("Bounties", "Active Bounties"):
        return _build_bounties_embed(session_id, selected_quest_id=selected_quest_id)
    elif tab == "Goals":
        return _build_campaign_goals_embed(session_id)
    elif tab == "Caseboard":
        return _build_caseboard_embed(session_id, selected_suspect=selected_suspect)
    elif tab == "History":
        return _build_history_embed(session_id, selected_quest_id=selected_quest_id)
    return _build_main_quest_embed(session_id)

def _build_bounty_board_embed(session: dict, bounties: list[dict]) -> discord.Embed:
    from mechanics.world.locations import get_zone_location_name
    from mechanics.narrative.bounty import get_bounty_board_title_name
    scen_key = session.get("scenario", "fantasy") if session else "fantasy"
    raw_loc = session.get("current_location", "Local Region") if session else "Local Region"
    loc = get_zone_location_name(raw_loc)
    board_title, board_emoji = get_bounty_board_title_name(scen_key)

    embed = discord.Embed(
        title=f"{board_emoji} {board_title} — {loc}",
        description="Pick a posting from the dropdown below to accept it into your active Quest Log!",
        color=discord.Color.gold()
    )

    if not bounties:
        embed.add_field(name="No Bounties Available", value="Click **Refresh Board** to request new postings from local contacts.", inline=False)
        return embed

    for idx, b in enumerate(bounties, start=1):
        rxp = b.get("reward_xp", 150)
        rgold = b.get("reward_gold", 40)
        ritem = b.get("reward_item", "")
        rew_parts = [f"{rxp} XP", f"{rgold} Gold"]
        if ritem:
            rew_parts.append(f"Item: {ritem}")
        rew_str = ", ".join(rew_parts)
        q_type = b.get("quest_type", "Side Bounty")
        icon = _quest_type_icon(q_type)

        embed.add_field(
            name=f"{idx}. {icon} {b['title']} [{q_type}]",
            value=f"**Objective:** {b['objective']}\n**Rewards:** {rew_str}",
            inline=False
        )

    return embed


