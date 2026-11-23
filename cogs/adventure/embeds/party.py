"""Party vitals, entity tracker formatting, choice labels, and shared Discord embed helpers."""
from __future__ import annotations

import json
import re
import unicodedata

import discord
from discord import app_commands

import db
from character_data import get_item_icon
from game_engine.choice_icons import (
    get_choice_emoji as _get_choice_emoji,  # static-check: ignore[unused-import]
    get_choice_quest_icon as _get_choice_quest_icon,  # static-check: ignore[unused-import]
    get_choice_skill_emoji as _get_choice_skill_emoji,  # static-check: ignore[unused-import]
)
from mechanics.combat.status_effects import format_status_badge
from mechanics.world.locations import format_tiered_location_string
from scenario_data import DEFAULT_SCENARIO, ScenarioError, load_scenarios

MODE_LABELS = {"solo": "Solo", "turn": "Multiplayer (Turn-based)", "sync": "Multiplayer (Synchronized)"}

_RESULT_COLORS = {
    "crit_success": discord.Color.from_rgb(46, 204, 113),   # emerald green
    "success":      discord.Color.from_rgb(26, 188, 156),   # teal
    "fail":         discord.Color.from_rgb(230, 126, 34),   # amber
    "crit_fail":    discord.Color.from_rgb(231, 76, 60),    # crimson
    "free":         discord.Color.from_rgb(88, 101, 242),   # blurple / narrative indigo
}

_RESULT_TITLES = {
    "crit_success": "✨ CRITICAL SUCCESS",
    "success":      "🎯 SUCCESS",
    "fail":         "⚠️ FAILURE",
    "crit_fail":    "💥 CRITICAL FAILURE",
    "free":         "📖 STORY PROGRESSION",
}


def _scenario_command_choices() -> list[app_commands.Choice[str]]:
    try:
        import scenario_variants
        choices = []
        scenarios = load_scenarios()
        # Only family roots: variants are picked in a follow-up Select (Discord caps static choices at 25).
        for key in scenario_variants.get_family_root_keys():
            entry = scenarios[key]
            label = entry.get("dropdown_label") or entry.get("display_name") or entry.get("name", key)
            emoji = entry.get("emoji", "")
            variant_count = len(scenario_variants.get_family_variants(key))
            suffix = f" · {variant_count} variants" if variant_count > 1 else ""
            base = f"{emoji} {label}".strip() if emoji and not label.startswith(emoji) else label
            name = base[:100 - len(suffix)] + suffix
            choices.append(app_commands.Choice(name=name, value=key))
        choices.append(app_commands.Choice(name="🛠️ Custom Scenario (Use Tags Parameter)", value="custom"))
        return choices
    except ScenarioError:
        return [
            app_commands.Choice(name="⚔️ Realms of Myth & Magic [Fantasy]", value=DEFAULT_SCENARIO),
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


def _format_status_list_for_embed(raw_statuses: list) -> list[str]:
    items: list[str] = []
    for s in (raw_statuses or []):
        if not s:
            continue
        badge = format_status_badge(s, include_duration=True).strip()
        if badge.startswith("[") and badge.endswith("]"):
            badge = badge[1:-1].strip()
        if badge:
            items.append(badge)
    return items


def _format_companion_kit_summary(entity: dict) -> str:
    loadout = entity.get("combat_loadout")
    if not isinstance(loadout, list) or not loadout:
        return ""
    cooldowns = entity.get("skill_cooldowns") if isinstance(entity.get("skill_cooldowns"), dict) else {}
    parts: list[str] = []
    for sk in loadout[:3]:
        if isinstance(sk, dict):
            sk_name = str(sk.get("name") or sk.get("id") or "Skill").strip()
            sk_id = str(sk.get("id") or "").strip()
        elif isinstance(sk, str) and sk.strip():
            sk_name = sk.strip()
            sk_id = sk_name
        else:
            continue
        cd = int(cooldowns.get(sk_id, 0) or 0) if sk_id else 0
        parts.append(f"{sk_name} [CD: {cd}t]" if cd > 0 else sk_name)
    return f"Kit: [{', '.join(parts)}]" if parts else ""


def _party_vitals_text(session: dict) -> str:
    """Renders the tracker: Lvl, Name, HP/MaxHP, MP/MaxMP, and
    active status effects for every human player and recruited party companion."""
    lines = []
    turn_order = session.get("turn_order") or []
    order_uids = [int(u) for u in turn_order if u is not None]
    chars_by_uid = (
        db.batch_load_party_characters(order_uids, session_id=session.get("id"))
        if order_uids
        else {}
    )
    for uid in turn_order:
        char = chars_by_uid.get(int(uid)) if uid is not None else None
        if not char:
            char = db.get_character(uid)
        if not char:
            continue
        marker = ""
        if session.get("mode") != "sync" and uid == db.current_turn_user_id(session):
            marker = "▶️ "
        status = _parse_status_effects(char.get("status_effects"))
        status_items = _format_status_list_for_embed(status)
        st = session.get("stealth_state") or {}
        has_vanished_buff = any("Hidden in Shadows" in s for s in status_items)
        from mechanics.stealth import is_actor_combat_vanished, is_actor_hidden
        if has_vanished_buff or is_actor_combat_vanished(session, uid):
            status_items = [s for s in status_items if "Hidden in Shadows" not in s]
            status_items.insert(0, "💨 Vanished")
        elif is_actor_hidden(session, uid):
            meter = int(st.get("detection_meter", 0))
            status_items.insert(0, f"🥷 Sneaking ({meter}%)")
        status_text = ", ".join(status_items) if status_items else "None"
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
                status_items = _format_status_list_for_embed(status)
                status_text = ", ".join(status_items) if status_items else "None"
                role_tag = f" ({npc['role']})" if npc.get("role") else ""
                sa_tag = " `[⚡ Special Agent]`" if npc.get("anomalous_npc_tag") == "special_agent" else ""
                arch = str(npc.get("combat_archetype") or npc.get("archetype") or "").strip()
                arch_tag = f" `[{arch}]`" if arch else ""
                kit_summary = _format_companion_kit_summary(npc)
                kit_tag = f" | {kit_summary}" if kit_summary else ""
                lines.append(f"🤝 Lvl {lvl} **{npc['name']}**{sa_tag}{arch_tag}{role_tag} — ❤️ {hp}/{max_hp} | "
                             f"💙 {mp}/{max_mp} | Status: {status_text}{kit_tag}")

    return _truncate_field_value("\n".join(lines), 1024)


def _location_text(session: dict, char_name: str = "") -> str:
    loc = session.get("current_location") or "Unknown"
    from mechanics.world.locations import get_zone_emoji, is_transit_location, parse_tiered_location
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
    from mechanics.world.mobility import is_dialogue_partner as _mobility_is_dp
    return _mobility_is_dp(name, dialogue_partners)


def is_matching_contact_dialogue_partner(contact: dict, partner_str: str) -> bool:
    """Returns True if the contact matches the specified dialogue partner string.
    Ensures that shared family surnames, honorifics, and East Asian surname-first order do not cause false positives."""
    if not contact or not partner_str:
        return False
    p_raw = str(partner_str).strip()
    if not p_raw or p_raw.lower() in ("none", "null"):
        return False

    c_name = str(contact.get("name") or "").strip()
    c_nid = str(contact.get("npc_id") or "").strip()

    p_norm = _norm_name(p_raw.replace("_", " "))
    c_name_norm = _norm_name(c_name.replace("_", " "))
    c_nid_norm = _norm_name(c_nid.replace("_", " "))

    if p_norm in (c_name_norm, c_nid_norm):
        return True

    role_title_prefixes = {
        "the", "elder", "lord", "lady", "sir", "madam", "madame", "captain", "dr", "mr", "ms", "mrs", "miss", "mx",
        "prof", "professor", "scholar", "guardian", "druid", "student", "council", "president", "vice",
        "secretary", "representative", "officer", "member", "guildmaster", "archivist", "warden", "coach",
        "chef", "nurse", "principal", "headmaster", "headmistress", "dean", "sensei",
    }

    def _strip_role_prefix(s: str) -> str:
        pts = s.replace("_", " ").strip().split()
        while len(pts) >= 2 and pts[0].lower().strip(".,") in role_title_prefixes:
            pts = pts[1:]
        return " ".join(pts)

    import namegen
    p_stripped = _strip_role_prefix(p_raw)
    c_stripped = _strip_role_prefix(c_name)
    p_first, p_last = namegen.extract_first_and_last_name(p_stripped)
    c_first, c_last = namegen.extract_first_and_last_name(c_stripped)
    if p_first and p_last and c_first and c_last:
        return _norm_name(p_first) == _norm_name(c_first) and (
            _norm_name(namegen.normalize_base_surname(p_last)) == _norm_name(namegen.normalize_base_surname(c_last))
        )

    p_toks = namegen.get_unique_person_tokens(p_raw.replace("_", " "), min_len=2)
    c_toks = namegen.get_unique_person_tokens(c_name, min_len=2)
    if p_toks and c_toks:
        c_given = _norm_name(c_first) if c_first else ""
        p_given = _norm_name(p_first) if p_first else ""
        if c_given and p_given and c_given == p_given:
            return True
        if any(" " in t for t in (p_toks & c_toks)):
            return True
    return False


def _format_tracker_entity(
    entity: dict,
    dialogue_partners: list = None,
    show_vitals: bool = True,
    *,
    show_enemy_hp: bool = True,
    show_enemy_intent: bool = True,
) -> str:
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
    is_compulsive_anom = bool(
        (entity.get("is_anomalous_entity") or str(entity.get("npc_type") or "").lower() == "anomaly")
        and (str(entity.get("sapience") or "").lower() == "compulsive" or entity.get("pattern_observable"))
    )
    conv_prefix = ("👁️ " if is_compulsive_anom else "💬 ") if is_conv else ""

    tier_rank = entity.get("tier_rank")
    tier_name = str(entity.get("tier") or "").lower()
    tier_badge = ""
    if tier_rank == 5 or tier_name == "boss":
        tier_badge = " `[Boss]`"
    elif tier_rank == 4 or tier_name == "miniboss":
        tier_badge = " `[Miniboss]`"
    elif tier_rank == 3 or tier_name == "elite":
        tier_badge = " `[Elite]`"

    if entity.get("is_summon"):
        tier_badge += " `[🤖 Construct]`"
    elif entity.get("is_disguised") or entity.get("uncanny_presence"):
        tier_badge += " `[🎭 Uncanny Presence]`"
    elif (
        entity.get("is_anomalous_entity")
        or str(entity.get("npc_type") or "").lower() == "anomaly"
        or entity.get("anomalous_npc_tag") == "anomaly_entity"
    ):
        tier_badge += " `[👁️ Anomaly]`"
    elif entity.get("anomalous_npc_tag") == "special_agent":
        tier_badge += " `[⚡ Special Agent]`"
    elif entity.get("anomalous_npc_tag") == "civilian":
        tier_badge += " `[Civilian]`"

    intent = entity.get("intent")
    intent_line = f"\n   ↳ ⚡ *Intent: {intent}*" if (intent and show_enemy_intent) else ""
    act_tag = str(entity.get("activity_tag") or "").strip()
    act_mode = str(entity.get("activity_mode") or "").strip().lower()
    act_badge = f" | 🎯 *{act_tag}*{' (Joined)' if act_mode == 'joined' else ''}" if act_tag else ""
    ep_tag = str(entity.get("epistemic_tag") or "").strip().lower()
    ep_badge_map = {
        "spotted_you": " | 👀 *Spotted You*",
        "hushed": " | 🤫 *Hushed*",
        "alibi_prepped": " | 🎭 *Alibi*",
        "co_conspirator": " | 🤝 *Co-Conspirator*",
    }
    ep_badge = ep_badge_map.get(ep_tag, "")
    tell_txt = str(entity.get("visible_tell_text") or "").strip() if bool(entity.get("telltale_revealed")) else ""
    tell_line = f"\n   ↳ 👁️ *Tell: {tell_txt}*" if tell_txt else ""
    if ep_badge:
        act_badge += ep_badge

    status_items = _format_status_list_for_embed(status)
    if mood and str(mood).strip() and str(mood).strip() not in status_items:
        status_items.append(str(mood).strip())

    if entity.get("is_spotlight") is False and not is_conv and not (
        entity.get("is_anomalous_entity") or str(entity.get("npc_type") or "").lower() == "anomaly"
    ):
        return f"• **{name}**{tier_badge}{role_str}{act_badge}{tell_line}"

    if hp is not None or level is not None:
        line = f"Lvl {level} " if level is not None else ""
        line += f"{conv_prefix}**{name}**{tier_badge}{role_str}"
        if hp is not None and show_enemy_hp:
            line += f" — ❤️ {hp}/{max_hp}"
            if entity.get("temp_hp"):
                line += f" (+🛡️{int(entity['temp_hp'])})"
            if mp is not None and mp > 0:
                line += f" | 💙 {mp}/{max_mp}"
        max_stab = entity.get("max_stability")
        if max_stab is not None and int(max_stab or 0) > 0:
            cur_stab = int(entity.get("stability", max_stab) or 0)
            if entity.get("is_breached"):
                b_turns = int(entity.get("breached_turns_left", 1) or 1)
                line += f" | 💥 **ANOMALY BREACHED! [{b_turns}T]**"
            else:
                line += f" | 💠 Poise {cur_stab}/{int(max_stab)}"
            vis_weak = list(entity.get("display_weaknesses") or entity.get("revealed_weaknesses") or entity.get("weaknesses") or [])
            hid_w = entity.get("hidden_weakness")
            if hid_w and hid_w != "?" and not entity.get("hidden_weakness_revealed"):
                vis_weak = [w for w in vis_weak if w != hid_w] + ["?"]
            if vis_weak:
                line += f" `Weak: {'/'.join(str(w).upper() for w in vis_weak)}`"
        tether_st = entity.get("tether_state") if isinstance(entity.get("tether_state"), dict) else None
        if tether_st and tether_st.get("has_tether"):
            if tether_st.get("sealed") or entity.get("tether_sealed"):
                line += " | 🔒 **Tether Sealed**"
            elif tether_st.get("reformed_once") or entity.get("tether_reformed_once") or entity.get("dossier_revealed"):
                v_nm = str(tether_st.get("vessel_name") or "Hidden Vessel")
                line += f" | 🏺 *Tether: {v_nm}*"
        if entity.get("is_summon"):
            q_act_emb = entity.get("queued_windup") or entity.get("queued_construct_action")
            if isinstance(q_act_emb, dict):
                q_sk = q_act_emb.get("skill_name") or q_act_emb.get("name")
                if q_sk:
                    line += f" | ⚡ *Primed: {q_sk}*"
        aggro_target = str(entity.get("aggro_target_name") or "").strip()
        if aggro_target and hp is not None:
            if entity.get("aggro_mode") == "taunted":
                line += f" | 🔒 **Taunted: {aggro_target}**"
            else:
                line += f" | 🎯 *Aggro: {aggro_target}*"
        if entity.get("_is_party_npc"):
            kit_summary = _format_companion_kit_summary(entity)
            if kit_summary:
                line += f" | {kit_summary}"
        status_text = ", ".join(status_items) if status_items else "None"
        line += f" | Status: {status_text}"
        telegraph = entity.get("telegraphed_skill")
        if show_enemy_intent and isinstance(telegraph, dict) and telegraph and hp is not None:
            sk_name = str(
                telegraph.get("skill_name")
                or telegraph.get("telegraphed_label")
                or telegraph.get("name")
                or "Signature Attack"
            ).strip()
            raw_pct = entity.get("stagger_pct")
            if raw_pct is None:
                thr = max(1, int(telegraph.get("interrupt_threshold", 1) or 1))
                acc = max(0, int(telegraph.get("accumulated_interrupt_damage", 0) or 0))
                s_pct = max(0, min(100, int(round((acc / float(thr)) * 100))))
            else:
                s_pct = max(0, min(100, int(raw_pct or 0)))
            filled = max(0, min(5, round(s_pct / 20)))
            bar = ("█" * filled) + ("░" * (5 - filled))
            state_lbl = "Breaking!" if s_pct >= 65 else "Charging"
            line += f"\n   ↳ ⚠️ **CHARGING: {sk_name}** [Stagger {bar} {s_pct}% — {state_lbl}]"
        line += f"{act_badge}{intent_line}{tell_line}"
        return line
    else:
        status_text = ", ".join(status_items) if status_items else "Neutral"
        return f"{conv_prefix}**{name}**{tier_badge}{role_str} | Status: {status_text}{act_badge}{intent_line}{tell_line}"


def _tracker_group_text(
    entities: list,
    max_len: int = 1000,
    dialogue_partners: list = None,
    show_vitals: bool = True,
    *,
    show_enemy_hp: bool = True,
    show_enemy_intent: bool = True,
) -> str:
    lines = []
    current_len = 0
    for e in entities:
        line = _format_tracker_entity(
            e,
            dialogue_partners=dialogue_partners,
            show_vitals=show_vitals,
            show_enemy_hp=show_enemy_hp,
            show_enemy_intent=show_enemy_intent,
        )
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
    cleaned = re.sub(
        r'^(?:[\U00010000-\U0010ffff\u2600-\u27bf\u2300-\u23ff\u2b50\u2b55\u200d\ufe0f\s]+|\s*\[[A-Za-z0-9\u00C0-\u024F\u4e00-\u9fff/: _\'\",|+\u2013\u2014-]+\]\s*)+',
        '',
        str(text),
    ).strip()
    return cleaned if cleaned else str(text).strip()


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


def _choice_button_label(idx: int, choice: dict, prefix: str, show_percentages: bool = True) -> str:
    """Builds a button label keeping the whole label within Discord's 80-character limit."""
    label_text = _strip_leading_emojis(choice.get("label", ""))
    if "%" in label_text:
        full_text = label_text.strip()
        first_char = full_text[0] if full_text else ""
        if ord(first_char) > 255:
            full_text = full_text[1:].strip()
        if not show_percentages:
            full_text = re.sub(r'\b\d+%\s*', '', full_text).strip()
        return full_text[:80]

    head = f"{prefix}" if show_percentages else ""
    budget = 80 - len(head)
    if len(label_text) > budget:
        label_text = label_text[:max(0, budget - 1)].rstrip() + "…"
    return f"{head}{label_text}"
